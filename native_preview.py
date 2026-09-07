#!/usr/bin/env python3
"""Dependency-free diagnostic mesh rasterizer for AXM Game Asset Forge."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from native_geometry import Mesh, face_normal, triangulate
from native_pbr import png_bytes


@dataclass(frozen=True, slots=True)
class ViewSpec:
    name: str
    u_axis: int
    v_axis: int
    depth_axis: int
    depth_sign: float


VIEWS = {
    "front": ViewSpec("front", 0, 1, 2, 1.0),
    "side": ViewSpec("side", 2, 1, 0, 1.0),
    "top": ViewSpec("top", 0, 2, 1, 1.0),
}


def _sha256(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _edge(ax: float, ay: float, bx: float, by: float, px: float, py: float) -> float:
    return (px - ax) * (by - ay) - (py - ay) * (bx - ax)


def render(mesh: Mesh, *, view: str = "front", size: int = 128, margin: float = 0.06) -> dict[str, object]:
    if view not in VIEWS:
        raise ValueError(f"unknown view {view}")
    if size < 16:
        raise ValueError("preview size must be >=16")
    spec = VIEWS[view]
    tri = triangulate(mesh)
    if not tri.vertices or not tri.faces:
        raise ValueError("preview needs triangle geometry")

    projected = [(vertex[spec.u_axis], vertex[spec.v_axis], vertex[spec.depth_axis] * spec.depth_sign) for vertex in tri.vertices]
    us = [value[0] for value in projected]
    vs = [value[1] for value in projected]
    ds = [value[2] for value in projected]
    min_u, max_u = min(us), max(us)
    min_v, max_v = min(vs), max(vs)
    min_d, max_d = min(ds), max(ds)
    span_u = max(max_u - min_u, 1e-9)
    span_v = max(max_v - min_v, 1e-9)
    span_d = max(max_d - min_d, 1e-9)
    pad = size * margin
    scale_x = (size - 1 - 2.0 * pad) / span_u
    scale_y = (size - 1 - 2.0 * pad) / span_v

    screen = [
        (pad + (u - min_u) * scale_x, size - 1 - (pad + (v - min_v) * scale_y), depth)
        for u, v, depth in projected
    ]
    depth_buffer = [float("-inf")] * (size * size)
    silhouette = bytearray(size * size)
    normal_pixels = bytearray(size * size * 3)

    for face in tri.faces:
        a, b, c = face
        ax, ay, ad = screen[a]
        bx, by, bd = screen[b]
        cx, cy, cd = screen[c]
        area = _edge(ax, ay, bx, by, cx, cy)
        if abs(area) <= 1e-10:
            continue
        lo_x = max(0, int(min(ax, bx, cx)))
        hi_x = min(size - 1, int(max(ax, bx, cx)) + 1)
        lo_y = max(0, int(min(ay, by, cy)))
        hi_y = min(size - 1, int(max(ay, by, cy)) + 1)
        normal = face_normal(tri, face)
        normal_rgb = tuple(max(0, min(255, round((component * 0.5 + 0.5) * 255.0))) for component in normal)
        for py in range(lo_y, hi_y + 1):
            y = py + 0.5
            for px in range(lo_x, hi_x + 1):
                x = px + 0.5
                w0 = _edge(bx, by, cx, cy, x, y) / area
                w1 = _edge(cx, cy, ax, ay, x, y) / area
                w2 = 1.0 - w0 - w1
                if w0 < -1e-8 or w1 < -1e-8 or w2 < -1e-8:
                    continue
                depth = ad * w0 + bd * w1 + cd * w2
                index = py * size + px
                if depth <= depth_buffer[index]:
                    continue
                depth_buffer[index] = depth
                silhouette[index] = 255
                base = index * 3
                normal_pixels[base:base + 3] = bytes(normal_rgb)

    depth_pixels = bytearray(size * size)
    covered = 0
    for index, depth in enumerate(depth_buffer):
        if depth == float("-inf"):
            continue
        covered += 1
        depth_pixels[index] = max(0, min(255, round((depth - min_d) / span_d * 255.0)))

    silhouette_png = png_bytes(size, size, 1, bytes(silhouette))
    depth_png = png_bytes(size, size, 1, bytes(depth_pixels))
    normal_png = png_bytes(size, size, 3, bytes(normal_pixels))
    return {
        "view": view,
        "size": [size, size],
        "covered_pixels": covered,
        "coverage": covered / (size * size),
        "silhouette_png": silhouette_png,
        "depth_png": depth_png,
        "normal_png": normal_png,
        "hashes": {
            "silhouette": _sha256(silhouette_png),
            "depth": _sha256(depth_png),
            "normal": _sha256(normal_png),
        },
    }


def write_preview(mesh: Mesh, output: str | Path, *, size: int = 128, views=("front", "side", "top")) -> dict[str, object]:
    root = Path(output)
    root.mkdir(parents=True, exist_ok=True)
    reports = []
    for view in views:
        result = render(mesh, view=view, size=size)
        for kind in ("silhouette", "depth", "normal"):
            (root / f"{view}-{kind}.png").write_bytes(result.pop(f"{kind}_png"))
        reports.append(result)
    return {"mesh": mesh.name, "views": reports, "truth": "Diagnostic software rasterizer only; not an in-engine acceptance render."}
