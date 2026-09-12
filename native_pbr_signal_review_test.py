#!/usr/bin/env python3
from __future__ import annotations

import binascii
import hashlib
import json
from pathlib import Path
import struct
import tempfile
import unittest
import zlib

from native_pbr_signal_review import (
    SUPPORTED_PBR_SCHEMA,
    review_native_pbr,
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


def sha(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def make_native_pbr_fixture(root: Path, *, extra: bool = False) -> Path:
    maps = {}

    def add(name: str, pixel_fn):
        data = png_rgba(8, 8, pixel_fn)
        filename = f"{name}.png"
        (root / filename).write_bytes(data)
        maps[name] = {"file": filename, "sha256": sha(data), "channels": 4}

    add("base_color", lambda x, y: (30 + x * 17, 45 + y * 13, 70 + ((x + y) % 5) * 18, 255))

    def normal(x, y):
        nx = (x - 3.5) / 18.0
        ny = (y - 3.5) / 18.0
        nz = max(0.0, 1.0 - nx * nx - ny * ny) ** 0.5
        enc = lambda v: max(0, min(255, round((v * 0.5 + 0.5) * 255)))
        return enc(nx), enc(ny), enc(nz), 255

    add("normal", normal)
    add("roughness", lambda x, y: ((70 + x * 11 + y * 5),) * 3 + (255,))
    add("metallic", lambda x, y: ((20 + x * 15 + y * 3),) * 3 + (255,))
    add("height", lambda x, y: ((80 + x * 7 + y * 9),) * 3 + (255,))
    add("ao", lambda x, y: ((150 + x * 6 + y * 4),) * 3 + (255,))
    add("orm", lambda x, y: (150 + x * 6, 70 + y * 9, 20 + (x + y) * 7, 255))
    if extra:
        add("future_map", lambda x, y: (x * 20, y * 20, 100, 255))

    manifest = {
        "schema": SUPPORTED_PBR_SCHEMA,
        "kind": "painted_metal",
        "seed": 7,
        "size": [8, 8],
        "maps": maps,
        "truth": {"deterministic": True, "physically_measured": False},
    }
    path = root / "material.json"
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


class NativePbrSignalReviewTests(unittest.TestCase):
    def test_semantic_native_pbr_maps_are_audited(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            path = make_native_pbr_fixture(root)
            review = review_native_pbr(path)
            self.assertIn(review["status"], {"PASS", "PASS_WITH_WARNINGS"})
            self.assertEqual(review["manifest_hash_mismatches"], [])
            rows = {row["id"]: row for row in review["audit"]["entries"]}
            self.assertEqual(rows["base_color"]["channel"], "base-color")
            self.assertEqual(rows["ao"]["channel"], "ambient-occlusion")
            self.assertEqual(rows["orm"]["channel"], "unassigned")
            self.assertFalse(review["truth_boundary"]["filename_semantics_inferred"])

    def test_manifest_hash_drift_holds_review(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            path = make_native_pbr_fixture(root)
            (root / "roughness.png").write_bytes(
                png_rgba(8, 8, lambda x, y: ((20 + x * 20),) * 3 + (255,))
            )
            review = review_native_pbr(path)
            self.assertEqual(review["status"], "HOLD")
            self.assertEqual(review["manifest_hash_mismatches"][0]["map_id"], "roughness")

    def test_unknown_future_map_is_preserved_as_hold_direction(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            path = make_native_pbr_fixture(root, extra=True)
            review = review_native_pbr(path)
            self.assertEqual(review["held_unknown_map_keys"], ["future_map"])
            self.assertEqual(review["status"], "PASS_WITH_WARNINGS")

    def test_actual_native_pbr_generator_round_trip(self) -> None:
        from native_pbr import write_painted_metal

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            write_painted_metal(root, size=16, seed=17)
            review = review_native_pbr(root / "material.json")
            self.assertNotEqual(review["status"], "HOLD")
            self.assertEqual(review["manifest_hash_mismatches"], [])
            self.assertEqual(
                {row["id"] for row in review["audit"]["entries"]},
                {"base_color", "normal", "roughness", "metallic", "height", "ao", "orm"},
            )


if __name__ == "__main__":
    unittest.main()
