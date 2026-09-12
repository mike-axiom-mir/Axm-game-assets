#!/usr/bin/env python3
from __future__ import annotations

import binascii
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
import zlib

from native_material_signal_audit import (
    REQUEST_SCHEMA,
    audit_material_request,
    decode_png_rgba,
)


def _chunk(kind: bytes, payload: bytes) -> bytes:
    return (
        struct.pack(">I", len(payload))
        + kind
        + payload
        + struct.pack(">I", binascii.crc32(kind + payload) & 0xFFFFFFFF)
    )


def png_rgba(width: int, height: int, pixel_fn) -> bytes:
    raw = bytearray()
    for y in range(height):
        raw.append(0)
        for x in range(width):
            raw.extend(pixel_fn(x, y))
    return (
        b"\x89PNG\r\n\x1a\n"
        + _chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
        + _chunk(b"IDAT", zlib.compress(bytes(raw), 9))
        + _chunk(b"IEND", b"")
    )


def request(entries, family_id="fixture"):
    return {"schema": REQUEST_SCHEMA, "family_id": family_id, "entries": entries}


class MaterialSignalAuditTests(unittest.TestCase):
    def write(self, root: Path, name: str, data: bytes) -> None:
        (root / name).write_bytes(data)

    def test_clean_pbr_family_passes(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            base = png_rgba(
                8, 8,
                lambda x, y: (
                    40 + x * 14,
                    62 + y * 10,
                    90 + ((x + y) % 5) * 12,
                    255,
                ),
            )
            rough = png_rgba(
                8, 8,
                lambda x, y: (
                    (60 + x * 17 + y * 5) % 220 + 20,
                    (60 + x * 17 + y * 5) % 220 + 20,
                    (60 + x * 17 + y * 5) % 220 + 20,
                    255,
                ),
            )

            def normal(x: int, y: int) -> tuple[int, int, int, int]:
                nx = (x - 3.5) / 18.0
                ny = (y - 3.5) / 18.0
                nz = max(0.0, 1.0 - nx * nx - ny * ny) ** 0.5
                encode = lambda v: max(0, min(255, round((v * 0.5 + 0.5) * 255)))
                return encode(nx), encode(ny), encode(nz), 255

            normal_png = png_rgba(8, 8, normal)
            self.write(root, "base.png", base)
            self.write(root, "rough.png", rough)
            self.write(root, "normal.png", normal_png)
            report = audit_material_request(
                request(
                    [
                        {"id": "base", "channel": "base-color", "path": "base.png"},
                        {"id": "rough", "channel": "roughness", "path": "rough.png"},
                        {"id": "normal", "channel": "normal", "path": "normal.png"},
                    ]
                ),
                root,
            )
            self.assertEqual(report["status"], "PASS")
            self.assertEqual(report["family_warnings"], [])
            self.assertTrue(report["report_digest"].startswith("sha256:"))
            normal_row = next(row for row in report["entries"] if row["id"] == "normal")
            self.assertGreater(normal_row["signal"]["normal"]["mean_z"], 0.8)
            self.assertGreaterEqual(normal_row["signal"]["normal"]["valid_length_share"], 0.99)

    def test_colored_scalar_map_is_warned_not_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            data = png_rgba(8, 8, lambda x, y: (20 + x * 20, 30 + y * 10, 180, 255))
            self.write(root, "rough.png", data)
            report = audit_material_request(
                request([{"id": "rough", "channel": "roughness", "path": "rough.png"}]),
                root,
            )
            self.assertEqual(report["status"], "PASS_WITH_WARNINGS")
            self.assertIn("scalar-channel-color-leak", report["entries"][0]["warnings"])

    def test_duplicate_payload_across_channels_is_visible(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            data = png_rgba(8, 8, lambda x, y: (30 + x * 12, 40 + y * 12, 50 + (x + y) * 8, 255))
            self.write(root, "same.png", data)
            self.write(root, "also-same.png", data)
            report = audit_material_request(
                request(
                    [
                        {"id": "a", "channel": "base-color", "path": "same.png"},
                        {"id": "b", "channel": "roughness", "path": "also-same.png"},
                    ]
                ),
                root,
            )
            self.assertEqual(report["status"], "PASS_WITH_WARNINGS")
            self.assertIn(
                "duplicate-payload-across-channels:base-color,roughness",
                report["family_warnings"],
            )

    def test_fully_transparent_signal_is_warned(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            data = png_rgba(8, 8, lambda x, y: (x * 20, y * 20, 100, 0))
            self.write(root, "opacity.png", data)
            report = audit_material_request(
                request([{"id": "alpha", "channel": "opacity", "path": "opacity.png"}]),
                root,
            )
            self.assertIn("fully-transparent-signal", report["entries"][0]["warnings"])

    def test_corrupt_png_crc_becomes_hold(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            data = bytearray(png_rgba(2, 2, lambda x, y: (20, 20, 20, 255)))
            idat = data.index(b"IDAT")
            data[idat + 5] ^= 0x01
            self.write(root, "broken.png", bytes(data))
            report = audit_material_request(
                request([{"id": "broken", "channel": "base-color", "path": "broken.png"}]),
                root,
            )
            self.assertEqual(report["status"], "HOLD")
            self.assertEqual(report["entries"][0]["status"], "HOLD")
            self.assertIn("CRC mismatch", report["entries"][0]["error"])

    def test_path_escape_becomes_hold(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            outside = root.parent / f"{root.name}-outside.png"
            outside.write_bytes(png_rgba(1, 1, lambda x, y: (1, 2, 3, 255)))
            try:
                report = audit_material_request(
                    request([{"id": "escape", "channel": "base-color", "path": "../" + outside.name}]),
                    root,
                )
                self.assertEqual(report["status"], "HOLD")
                self.assertIn("unsafe", report["entries"][0]["error"])
            finally:
                outside.unlink(missing_ok=True)

    @unittest.skipUnless(hasattr(os, "symlink"), "symlink unsupported")
    def test_symlink_payload_becomes_hold(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            real = root / "real.png"
            real.write_bytes(png_rgba(1, 1, lambda x, y: (1, 2, 3, 255)))
            link = root / "link.png"
            try:
                os.symlink(real.name, link)
            except (OSError, NotImplementedError):
                self.skipTest("symlink creation unavailable")
            report = audit_material_request(
                request([{"id": "link", "channel": "base-color", "path": "link.png"}]),
                root,
            )
            self.assertEqual(report["status"], "HOLD")
            self.assertIn("symlink", report["entries"][0]["error"])

    def test_png_filter_decoder_round_trip(self) -> None:
        data = png_rgba(3, 2, lambda x, y: (x * 20, y * 30, 70, 255))
        width, height, rgba = decode_png_rgba(data)
        self.assertEqual((width, height), (3, 2))
        self.assertEqual(rgba[:4], bytes((0, 0, 70, 255)))
        self.assertEqual(rgba[-4:], bytes((40, 30, 70, 255)))

    def test_duplicate_request_key_is_rejected_by_cli(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            req = root / "request.json"
            req.write_text(
                '{"schema":"axm.game-assets.material-audit-request/v0.1",'
                '"family_id":"a","family_id":"b","entries":[]}\n',
                encoding="utf-8",
            )
            completed = subprocess.run(
                [sys.executable, "native_material_signal_audit.py", str(req)],
                cwd=Path(__file__).resolve().parent,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(completed.returncode, 2)
            self.assertIn("duplicate JSON key", completed.stderr)

    def test_cli_output_is_create_only(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self.write(root, "base.png", png_rgba(8, 8, lambda x, y: (x * 20, y * 20, 50, 255)))
            req = root / "request.json"
            req.write_text(
                json.dumps(
                    request([{"id": "base", "channel": "base-color", "path": "base.png"}])
                )
                + "\n",
                encoding="utf-8",
            )
            out = root / "report.json"
            script = Path(__file__).resolve().parent / "native_material_signal_audit.py"
            first = subprocess.run(
                [sys.executable, str(script), str(req), "--output", str(out)],
                capture_output=True,
                text=True,
                check=False,
            )
            second = subprocess.run(
                [sys.executable, str(script), str(req), "--output", str(out)],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertEqual(second.returncode, 2)
            self.assertIn("already exists", second.stderr)


if __name__ == "__main__":
    unittest.main()
