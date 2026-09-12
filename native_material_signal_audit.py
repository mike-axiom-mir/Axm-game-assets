#!/usr/bin/env python3
"""Dependency-free Game Asset material payload + signal audit.

Mechanisms adapted from AXM Material / Surface Fabric v0.18.5-v0.18.6:
- payload-audit-core.js
- signal-audit-core.js
- tools/png-pixels.js

This is an AXM-native port into Game Asset Forge, not a runtime dependency on
Material / Surface Fabric. It deliberately separates byte/container health and
bounded pixel-signal warnings from aesthetic or physical-material judgment.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path, PurePosixPath
import stat
import struct
import sys
import zlib
from typing import Any

REQUEST_SCHEMA = "axm.game-assets.material-audit-request/v0.1"
REPORT_SCHEMA = "axm.game-assets.material-signal-audit/v0.1"
MAX_FILE_BYTES = 64 * 1024 * 1024
MAX_PIXELS = 32 * 1024 * 1024
MAX_DIMENSION = 8192
MAX_SAMPLES = 100_000
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
KNOWN_CHANNELS = {
    "base-color", "normal", "roughness", "metallic", "ambient-occlusion",
    "height", "displacement", "emissive", "opacity", "color-mask",
    "decal", "microdetail", "unassigned",
}
SCALAR_CHANNELS = {
    "roughness", "metallic", "ambient-occlusion", "height",
    "displacement", "opacity",
}


class MaterialAuditError(ValueError):
    pass


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _sha256(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _strict_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise MaterialAuditError(f"duplicate JSON key: {key}")
        out[key] = value
    return out


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_strict_pairs)
    except MaterialAuditError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise MaterialAuditError(f"invalid request JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise MaterialAuditError("request must contain one JSON object")
    return value


def _safe_relative(value: Any, label: str) -> PurePosixPath:
    if not isinstance(value, str) or not value or "\\" in value:
        raise MaterialAuditError(f"{label} must be a safe relative POSIX path")
    parts = value.split("/")
    path = PurePosixPath(value)
    if path.is_absolute() or path.as_posix() != value or any(p in {"", ".", ".."} for p in parts):
        raise MaterialAuditError(f"{label} is unsafe: {value!r}")
    return path


def _read_regular(root: Path, relative: Any) -> tuple[bytes, Path]:
    rel = _safe_relative(relative, "entry.path")
    path = root.joinpath(*rel.parts)
    current = root
    for part in rel.parts:
        current = current / part
        if current.is_symlink():
            raise MaterialAuditError(f"entry.path crosses symlink: {relative!r}")
    try:
        resolved = path.resolve(strict=True)
        resolved.relative_to(root)
        info = path.lstat()
    except (OSError, ValueError) as exc:
        raise MaterialAuditError(f"cannot resolve material payload {relative!r}") from exc
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        raise MaterialAuditError(f"material payload is not a regular file: {relative!r}")
    if info.st_size > MAX_FILE_BYTES:
        raise MaterialAuditError(f"material payload exceeds {MAX_FILE_BYTES} bytes: {relative!r}")
    return path.read_bytes(), path


def _chunks(data: bytes) -> list[tuple[str, bytes]]:
    if len(data) < 33 or data[:8] != PNG_SIGNATURE:
        raise MaterialAuditError("not a PNG file")
    out: list[tuple[str, bytes]] = []
    offset = 8
    saw_iend = False
    while offset + 12 <= len(data):
        length = struct.unpack_from(">I", data, offset)[0]
        type_bytes = data[offset + 4:offset + 8]
        try:
            kind = type_bytes.decode("ascii")
        except UnicodeDecodeError as exc:
            raise MaterialAuditError("PNG chunk type is not ASCII") from exc
        start = offset + 8
        end = start + length
        if end + 4 > len(data):
            raise MaterialAuditError(f"truncated PNG chunk: {kind or 'unknown'}")
        payload = data[start:end]
        expected_crc = zlib.crc32(type_bytes + payload) & 0xFFFFFFFF
        observed_crc = struct.unpack_from(">I", data, end)[0]
        if expected_crc != observed_crc:
            raise MaterialAuditError(f"PNG CRC mismatch in {kind}")
        out.append((kind, payload))
        offset = end + 4
        if kind == "IEND":
            saw_iend = True
            break
    if not saw_iend or offset != len(data):
        raise MaterialAuditError("PNG is missing a terminal IEND or has trailing bytes")
    return out


def _paeth(a: int, b: int, c: int) -> int:
    p = a + b - c
    pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
    return a if pa <= pb and pa <= pc else b if pb <= pc else c


def decode_png_rgba(data: bytes) -> tuple[int, int, bytes]:
    chunks = _chunks(data)
    ihdrs = [payload for kind, payload in chunks if kind == "IHDR"]
    if len(ihdrs) != 1 or len(ihdrs[0]) != 13 or chunks[0][0] != "IHDR":
        raise MaterialAuditError("PNG IHDR is missing, duplicated, malformed, or not first")
    ihdr = ihdrs[0]
    width, height = struct.unpack_from(">II", ihdr, 0)
    bit_depth, color_type, compression, filter_method, interlace = ihdr[8:13]
    if not width or not height or width > MAX_DIMENSION or height > MAX_DIMENSION:
        raise MaterialAuditError(f"unsupported PNG dimensions {width}x{height}")
    if width * height > MAX_PIXELS:
        raise MaterialAuditError("PNG exceeds pixel audit budget")
    channels_by_type = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}
    if bit_depth != 8 or color_type not in channels_by_type:
        raise MaterialAuditError(f"pixel audit supports 8-bit PNG color types 0/2/3/4/6; got {bit_depth}/{color_type}")
    if compression != 0 or filter_method != 0 or interlace != 0:
        raise MaterialAuditError("pixel audit supports standard non-interlaced PNG only")
    channels = channels_by_type[color_type]
    stride = width * channels
    idat = b"".join(payload for kind, payload in chunks if kind == "IDAT")
    if not idat:
        raise MaterialAuditError("PNG contains no IDAT data")
    try:
        inflated = zlib.decompress(idat)
    except zlib.error as exc:
        raise MaterialAuditError("PNG IDAT decompression failed") from exc
    if len(inflated) != height * (stride + 1):
        raise MaterialAuditError("unexpected decompressed PNG scanline size")

    raw = bytearray(width * height * channels)
    source = 0
    for y in range(height):
        filter_kind = inflated[source]
        source += 1
        row_start = y * stride
        for x in range(stride):
            value = inflated[source]
            source += 1
            left = raw[row_start + x - channels] if x >= channels else 0
            up = raw[row_start - stride + x] if y > 0 else 0
            up_left = raw[row_start - stride + x - channels] if y > 0 and x >= channels else 0
            if filter_kind == 0:
                out = value
            elif filter_kind == 1:
                out = (value + left) & 255
            elif filter_kind == 2:
                out = (value + up) & 255
            elif filter_kind == 3:
                out = (value + ((left + up) // 2)) & 255
            elif filter_kind == 4:
                out = (value + _paeth(left, up, up_left)) & 255
            else:
                raise MaterialAuditError(f"unsupported PNG filter {filter_kind}")
            raw[row_start + x] = out

    palette = next((payload for kind, payload in chunks if kind == "PLTE"), None)
    transparency = next((payload for kind, payload in chunks if kind == "tRNS"), None)
    if color_type == 3 and (not palette or len(palette) % 3):
        raise MaterialAuditError("palette PNG requires a valid PLTE chunk")

    rgba = bytearray(width * height * 4)
    for pixel in range(width * height):
        src = pixel * channels
        dst = pixel * 4
        if color_type == 0:
            gray = raw[src]
            rgba[dst:dst + 4] = bytes((gray, gray, gray, 255))
        elif color_type == 2:
            rgba[dst:dst + 4] = bytes((raw[src], raw[src + 1], raw[src + 2], 255))
        elif color_type == 3:
            index = raw[src]
            p = index * 3
            if palette is None or p + 2 >= len(palette):
                raise MaterialAuditError(f"palette index {index} is outside PLTE")
            alpha = transparency[index] if transparency is not None and index < len(transparency) else 255
            rgba[dst:dst + 4] = bytes((palette[p], palette[p + 1], palette[p + 2], alpha))
        elif color_type == 4:
            gray = raw[src]
            rgba[dst:dst + 4] = bytes((gray, gray, gray, raw[src + 1]))
        else:
            rgba[dst:dst + 4] = raw[src:src + 4]
    return width, height, bytes(rgba)


def inspect_image(data: bytes) -> dict[str, Any]:
    if data.startswith(PNG_SIGNATURE):
        chunks = _chunks(data)
        ihdrs = [payload for kind, payload in chunks if kind == "IHDR"]
        if len(ihdrs) != 1 or len(ihdrs[0]) != 13 or chunks[0][0] != "IHDR":
            raise MaterialAuditError("PNG IHDR is missing, duplicated, malformed, or not first")
        ihdr = ihdrs[0]
        width, height = struct.unpack_from(">II", ihdr, 0)
        bit_depth, color_type, compression, filter_method, interlace = ihdr[8:13]
        if not width or not height or width > MAX_DIMENSION or height > MAX_DIMENSION:
            raise MaterialAuditError(f"unsupported PNG dimensions {width}x{height}")
        if width * height > MAX_PIXELS:
            raise MaterialAuditError("PNG exceeds pixel audit budget")
        if compression != 0 or filter_method != 0:
            raise MaterialAuditError("PNG uses unsupported compression/filter method")
        return {
            "mime": "image/png",
            "width": width,
            "height": height,
            "bit_depth": bit_depth,
            "color_type": color_type,
            "interlace": interlace,
            "pixel_decoder": (
                "rgba8-noninterlaced"
                if bit_depth == 8 and color_type in {0, 2, 3, 4, 6} and interlace == 0
                else None
            ),
        }

    if len(data) >= 3 and data[:3] == b"\xff\xd8\xff":
        if len(data) < 4 or data[-2:] != b"\xff\xd9":
            raise MaterialAuditError("JPEG is missing terminal EOI")
        width = height = None
        offset = 2
        sof = {0xC0,0xC1,0xC2,0xC3,0xC5,0xC6,0xC7,0xC9,0xCA,0xCB,0xCD,0xCE,0xCF}
        while offset < len(data):
            while offset < len(data) and data[offset] != 0xFF:
                offset += 1
            while offset < len(data) and data[offset] == 0xFF:
                offset += 1
            if offset >= len(data):
                break
            marker = data[offset]
            offset += 1
            if marker in {0xD9, 0xDA}:
                break
            if marker == 0x01 or 0xD0 <= marker <= 0xD7:
                continue
            if offset + 2 > len(data):
                raise MaterialAuditError("JPEG segment length is truncated")
            length = struct.unpack_from(">H", data, offset)[0]
            if length < 2 or offset + length > len(data):
                raise MaterialAuditError("JPEG segment length is invalid")
            if marker in sof and length >= 8:
                height = struct.unpack_from(">H", data, offset + 3)[0]
                width = struct.unpack_from(">H", data, offset + 5)[0]
                break
            offset += length
        if not width or not height:
            raise MaterialAuditError("JPEG dimensions could not be established")
        if width > MAX_DIMENSION or height > MAX_DIMENSION or width * height > MAX_PIXELS:
            raise MaterialAuditError(f"JPEG exceeds audit dimensions/pixel budget: {width}x{height}")
        return {"mime": "image/jpeg", "width": width, "height": height, "pixel_decoder": None}

    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        declared = struct.unpack_from("<I", data, 4)[0] + 8
        if declared != len(data):
            raise MaterialAuditError("WebP RIFF size mismatch")
        width = height = None
        primary = None
        offset = 12
        while offset + 8 <= len(data):
            kind = data[offset:offset + 4]
            length = struct.unpack_from("<I", data, offset + 4)[0]
            start = offset + 8
            end = start + length
            if end > len(data):
                raise MaterialAuditError("WebP chunk exceeds file length")
            payload = data[start:end]
            if kind == b"VP8X" and len(payload) >= 10:
                primary = "VP8X"
                width = 1 + int.from_bytes(payload[4:7], "little")
                height = 1 + int.from_bytes(payload[7:10], "little")
            elif kind == b"VP8 " and len(payload) >= 10 and width is None:
                primary = "VP8"
                if payload[3:6] != b"\x9d\x01\x2a":
                    raise MaterialAuditError("WebP VP8 frame signature mismatch")
                width = struct.unpack_from("<H", payload, 6)[0] & 0x3FFF
                height = struct.unpack_from("<H", payload, 8)[0] & 0x3FFF
            elif kind == b"VP8L" and len(payload) >= 5 and width is None:
                primary = "VP8L"
                if payload[0] != 0x2F:
                    raise MaterialAuditError("WebP VP8L signature mismatch")
                b1, b2, b3, b4 = payload[1:5]
                width = 1 + b1 + ((b2 & 0x3F) << 8)
                height = 1 + (b2 >> 6) + (b3 << 2) + ((b4 & 0x0F) << 10)
            offset = end + (length & 1)
        if offset != len(data):
            raise MaterialAuditError("WebP chunk layout mismatch")
        if not width or not height:
            raise MaterialAuditError("WebP dimensions could not be established")
        if width > MAX_DIMENSION or height > MAX_DIMENSION or width * height > MAX_PIXELS:
            raise MaterialAuditError(f"WebP exceeds audit dimensions/pixel budget: {width}x{height}")
        return {
            "mime": "image/webp",
            "width": width,
            "height": height,
            "primary_chunk": primary,
            "pixel_decoder": None,
        }

    raise MaterialAuditError("unknown image signature")


def signal_stats(rgba: bytes, width: int, height: int, channel: str) -> dict[str, Any]:
    pixels = width * height
    step = max(1, pixels // MAX_SAMPLES)
    sums = [0.0, 0.0, 0.0, 0.0]
    squares = [0.0, 0.0, 0.0, 0.0]
    gray = visible = partial_alpha = 0
    coarse: set[int] = set()
    edge_total = 0.0
    edge_count = 0
    normal_length_sum = normal_z_sum = 0.0
    normal_length_valid = 0
    samples = 0
    for pixel in range(0, pixels, step):
        off = pixel * 4
        r, g, b, a = rgba[off:off + 4]
        values = (r, g, b, a)
        for i, value in enumerate(values):
            sums[i] += value
            squares[i] += value * value
        gray += int(max(r, g, b) - min(r, g, b) <= 2)
        visible += int(a > 16)
        partial_alpha += int(0 < a < 255)
        coarse.add(((r >> 3) << 10) | ((g >> 3) << 5) | (b >> 3))
        x = pixel % width
        if x + 1 < width:
            nr, ng, nb = rgba[off + 4:off + 7]
            l0 = 0.2126 * r + 0.7152 * g + 0.0722 * b
            l1 = 0.2126 * nr + 0.7152 * ng + 0.0722 * nb
            edge_total += abs(l1 - l0) / 255.0
            edge_count += 1
        if channel == "normal":
            nx, ny, nz = r / 127.5 - 1.0, g / 127.5 - 1.0, b / 127.5 - 1.0
            length = math.sqrt(nx * nx + ny * ny + nz * nz)
            normal_length_sum += length
            normal_z_sum += nz
            normal_length_valid += int(0.5 <= length <= 1.5)
        samples += 1

    means = [value / max(1, samples) for value in sums]
    std = [math.sqrt(max(0.0, squares[i] / max(1, samples) - means[i] ** 2)) for i in range(4)]
    result: dict[str, Any] = {
        "samples": samples,
        "width": width,
        "height": height,
        "mean": {k: round(v, 6) for k, v in zip(("r", "g", "b", "a"), means)},
        "std": {k: round(v, 6) for k, v in zip(("r", "g", "b", "a"), std)},
        "grayscale_share": round(gray / max(1, samples), 6),
        "visible_alpha_share": round(visible / max(1, samples), 6),
        "partial_alpha_share": round(partial_alpha / max(1, samples), 6),
        "coarse_color_bins": len(coarse),
        "edge_energy": round(edge_total / max(1, edge_count), 6),
    }
    if channel == "normal":
        result["normal"] = {
            "mean_vector_length": round(normal_length_sum / max(1, samples), 6),
            "valid_length_share": round(normal_length_valid / max(1, samples), 6),
            "mean_z": round(normal_z_sum / max(1, samples), 6),
        }
    return result


def signal_warnings(channel: str, stats: dict[str, Any]) -> list[str]:
    warnings: list[str] = []
    rgb_std = [float(stats["std"][key]) for key in ("r", "g", "b")]
    if max(rgb_std) < 1.5 and float(stats["std"]["a"]) < 1.5:
        warnings.append("near-flat-signal")
    if channel in SCALAR_CHANNELS and float(stats["grayscale_share"]) < 0.95:
        warnings.append("scalar-channel-color-leak")
    if channel == "normal":
        normal = stats.get("normal", {})
        if float(stats["grayscale_share"]) > 0.95:
            warnings.append("normal-map-near-grayscale")
        if float(normal.get("mean_z", 0.0)) < 0.15:
            warnings.append("normal-positive-z-weak")
        if float(normal.get("valid_length_share", 0.0)) < 0.75:
            warnings.append("normal-vector-length-irregular")
    if channel == "base-color" and int(stats["coarse_color_bins"]) <= 4 and int(stats["samples"]) > 16:
        warnings.append("low-signal-diversity")
    if float(stats["visible_alpha_share"]) == 0.0:
        warnings.append("fully-transparent-signal")
    return sorted(set(warnings))


def audit_material_request(request: dict[str, Any], root: Path) -> dict[str, Any]:
    if request.get("schema") != REQUEST_SCHEMA:
        raise MaterialAuditError(f"request schema must be {REQUEST_SCHEMA}")
    family_id = request.get("family_id")
    if not isinstance(family_id, str) or not family_id.strip():
        raise MaterialAuditError("family_id must be non-empty")
    entries = request.get("entries")
    if not isinstance(entries, list) or not entries:
        raise MaterialAuditError("entries must be a non-empty list")

    seen_ids: set[str] = set()
    rows: list[dict[str, Any]] = []
    digest_groups: dict[str, list[tuple[str, str]]] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            raise MaterialAuditError("each entry must be an object")
        entry_id = entry.get("id")
        channel = entry.get("channel")
        if not isinstance(entry_id, str) or not entry_id.strip() or entry_id in seen_ids:
            raise MaterialAuditError("entry ids must be unique non-empty strings")
        seen_ids.add(entry_id)
        if channel not in KNOWN_CHANNELS:
            raise MaterialAuditError(f"entry {entry_id!r} has unsupported channel {channel!r}")
        try:
            data, _ = _read_regular(root, entry.get("path"))
            image = inspect_image(data)
            digest = _sha256(data)
            row: dict[str, Any] = {
                "id": entry_id,
                "channel": channel,
                "path": entry["path"],
                "status": "OBSERVED",
                "sha256": digest,
                "bytes": len(data),
                "image": image,
                "warnings": [],
            }
            digest_groups.setdefault(digest, []).append((entry_id, channel))
            if image["mime"] == "image/png" and image.get("pixel_decoder"):
                width, height, rgba = decode_png_rgba(data)
                stats = signal_stats(rgba, width, height, channel)
                row["signal"] = stats
                row["warnings"] = signal_warnings(channel, stats)
                if row["warnings"]:
                    row["status"] = "OBSERVED_WITH_WARNINGS"
            else:
                row["status"] = "STRUCTURE_ONLY"
                row["signal"] = None
                row["warnings"] = ["pixel-signal-unobserved"]
        except MaterialAuditError as exc:
            row = {
                "id": entry_id,
                "channel": channel,
                "path": entry.get("path"),
                "status": "HOLD",
                "error": str(exc),
                "warnings": [],
            }
        rows.append(row)

    family_warnings: list[str] = []
    for grouped in digest_groups.values():
        channels = sorted({channel for _, channel in grouped})
        if len(channels) > 1:
            family_warnings.append("duplicate-payload-across-channels:" + ",".join(channels))

    held = sum(row["status"] == "HOLD" for row in rows)
    unobserved = sum(row["status"] == "STRUCTURE_ONLY" for row in rows)
    warned = sum(bool(row.get("warnings")) for row in rows)
    status = "HOLD" if held else "PASS_WITH_WARNINGS" if warned or unobserved or family_warnings else "PASS"
    report: dict[str, Any] = {
        "schema": REPORT_SCHEMA,
        "family_id": family_id,
        "status": status,
        "entries": rows,
        "family_warnings": sorted(set(family_warnings)),
        "summary": {
            "entries": len(rows),
            "held_entries": held,
            "structure_only_entries": unobserved,
            "warned_entries": warned,
        },
        "truth_boundary": {
            "proves": [
                "bounded file/container identity for observed payloads",
                "bounded PNG pixel-signal statistics when the native decoder supports the PNG",
                "specific technical warning heuristics",
            ],
            "does_not_prove": [
                "aesthetic quality",
                "art-direction fit",
                "physical/PBR correctness",
                "engine parity",
                "AAA quality",
                "canonical adoption",
            ],
            "automatic_canon": False,
        },
        "provenance": {
            "mechanism_sources": [
                "mike-axiom-mir/axm-material-surface-fabric@v0.18.5 payload audit",
                "mike-axiom-mir/axm-material-surface-fabric@v0.18.6 signal audit",
            ],
            "implementation": "AXM Game Asset Forge native Python port",
        },
    }
    report["report_digest"] = _sha256(_canonical(report))
    return report


def _write_create_only(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("x", encoding="utf-8", newline="\n") as handle:
            json.dump(report, handle, indent=2, sort_keys=True, ensure_ascii=False)
            handle.write("\n")
    except FileExistsError as exc:
        raise MaterialAuditError(f"output already exists: {path}") from exc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit one explicit Game Asset material family without aesthetic overclaim")
    parser.add_argument("request", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        request_path = args.request.resolve()
        request = _load_json(request_path)
        report = audit_material_request(request, request_path.parent)
        if args.output:
            _write_create_only(args.output.resolve(), report)
    except MaterialAuditError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print(json.dumps(report, sort_keys=True, separators=(",", ":"), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
