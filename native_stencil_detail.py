#!/usr/bin/env python3
"""Geometric 3x5 stencil detail donor for AXM Game Asset Forge.

Adapted from Universal Creation's RTS detail layer at commit
a5cc708457b7e8f33e794fdac648ae65d15a0fb4
(`src/axm_uc/rts_detail.py`). The donor used real geometry for readable signage
instead of baking lettering into a screenshot. This Forge version returns native
Mesh state and imports no Universal Creation runtime.

The result is geometry only. It does not choose art direction, material, placement,
language, or canonical asset meaning for the caller.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Sequence

from native_geometry import Mesh, bounds, topology_report, write_obj

SCHEMA = "axm.game-assets.stencil-detail/v0.1"
DONOR = {
    "repo": "mike-axiom-mir/axm-universal-creation",
    "commit": "a5cc708457b7e8f33e794fdac648ae65d15a0fb4",
    "mechanism": "src/axm_uc/rts_detail.py geometric 3x5 lettering",
}

_GLYPHS = [
    "010101111101101","110101110101110","011100100100011","110101101101110",
    "111100110100111","111100110100100","011100101101011","101101111101101",
    "111010010010111","001001001101010","101101110101101","100100100100111",
    "101111111101101","101111111111101","010101101101010","110101110100100",
    "010101101111011","110101110101101","011100010001110","111010010010010",
    "101101101101111","101101101101010","101101111111101","101101010101101",
    "101101010010010","111001010100111","111101101101111","010110010010111",
    "110001010100111","110001010001110","101101111001001","111100110001110",
    "011100111101111","111001010010010","111101111101111","111101111001110",
]
FONT = dict(zip("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789", _GLYPHS))


class StencilDetailError(ValueError):
    pass


def _sha256(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _normalize_lines(lines: Sequence[str]) -> tuple[str, ...]:
    if not lines:
        raise StencilDetailError("at least one line is required")
    normalized: list[str] = []
    for index, line in enumerate(lines):
        if not isinstance(line, str):
            raise StencilDetailError(f"line {index} must be text")
        text = line.upper()
        if not text:
            raise StencilDetailError(f"line {index} must not be empty")
        unsupported = sorted({char for char in text if char != " " and char not in FONT})
        if unsupported:
            raise StencilDetailError(
                f"line {index} contains unsupported stencil characters: {unsupported!r}"
            )
        normalized.append(text)
    return tuple(normalized)


def stencil_mesh(
    lines: Sequence[str],
    *,
    width: float = 1.0,
    height: float = 1.0,
    z: float = 0.0,
    name: str = "stencil",
) -> Mesh:
    text = _normalize_lines(lines)
    if width <= 0.0 or height <= 0.0:
        raise StencilDetailError("width and height must be positive")
    max_chars = max(len(line) for line in text)
    cell = min(width / max(1, max_chars * 4), height / max(1, len(text) * 6))
    total_height = len(text) * 6 * cell
    vertices: list[tuple[float, float, float]] = []
    faces: list[tuple[int, int, int, int]] = []

    for row_index, line in enumerate(text):
        line_width = len(line) * 4 * cell
        left = -line_width * 0.5
        top = total_height * 0.5 - row_index * 6 * cell
        for char_index, char in enumerate(line):
            if char == " ":
                continue
            bits = FONT[char]
            for pixel_row in range(5):
                for pixel_col in range(3):
                    if bits[pixel_row * 3 + pixel_col] != "1":
                        continue
                    x0 = left + (char_index * 4 + pixel_col) * cell
                    x1 = x0 + cell * 0.90
                    y1 = top - pixel_row * cell
                    y0 = y1 - cell
                    start = len(vertices)
                    vertices.extend([
                        (x0, y0, z),
                        (x1, y0, z),
                        (x1, y1, z),
                        (x0, y1, z),
                    ])
                    faces.append((start, start + 1, start + 2, start + 3))
    if not faces:
        raise StencilDetailError("stencil contains no visible glyph cells")
    return Mesh(name, vertices, faces)


def stencil_receipt(
    lines: Sequence[str],
    *,
    width: float = 1.0,
    height: float = 1.0,
    z: float = 0.0,
    name: str = "stencil",
) -> tuple[Mesh, dict[str, Any]]:
    normalized = _normalize_lines(lines)
    mesh = stencil_mesh(normalized, width=width, height=height, z=z, name=name)
    lo, hi = bounds(mesh)
    topology = topology_report(mesh)
    receipt: dict[str, Any] = {
        "schema": SCHEMA,
        "name": name,
        "text": list(normalized),
        "requested_box": [width, height],
        "z": z,
        "bounds": {"min": list(lo), "max": list(hi)},
        "topology": topology,
        "provenance": {
            "donor": DONOR,
            "implementation": "AXM Game Asset Forge native geometry adaptation",
        },
        "truth_boundary": {
            "geometry_generated": True,
            "material_selected": False,
            "placement_selected": False,
            "art_direction_approved": False,
            "automatic_genome_mutation": False,
            "automatic_canon": False,
        },
    }
    receipt["receipt_digest"] = _sha256(_canonical(receipt))
    return mesh, receipt


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build deterministic native 3x5 stencil geometry")
    parser.add_argument("output_obj", type=Path)
    parser.add_argument("text", nargs="+")
    parser.add_argument("--width", type=float, default=1.0)
    parser.add_argument("--height", type=float, default=1.0)
    parser.add_argument("--name", default="stencil")
    parser.add_argument("--receipt", type=Path)
    args = parser.parse_args(argv)
    mesh, receipt = stencil_receipt(
        args.text,
        width=args.width,
        height=args.height,
        name=args.name,
    )
    if args.output_obj.exists():
        raise StencilDetailError(f"refusing to overwrite output: {args.output_obj}")
    write_obj(mesh, args.output_obj, include_normals=False)
    if args.receipt:
        if args.receipt.exists():
            raise StencilDetailError(f"refusing to overwrite receipt: {args.receipt}")
        args.receipt.parent.mkdir(parents=True, exist_ok=True)
        args.receipt.write_text(
            json.dumps(receipt, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    print(json.dumps({
        "name": mesh.name,
        "faces": len(mesh.faces),
        "receipt_digest": receipt["receipt_digest"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
