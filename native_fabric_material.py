#!/usr/bin/env python3
"""AXM deterministic woven fabric material authoring v0.1."""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path

from native_pbr import fbm, png_bytes


@dataclass(frozen=True, slots=True)
class FabricSpec:
    base_rgb: tuple[int, int, int] = (63, 70, 67)
    warp_threads: int = 58
    weft_threads: int = 54
    weave_depth: float = 0.12
    roughness: float = 0.72
    fiber_noise: float = 0.11
    thickness_hint_mm: float = 1.2


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def _u8(value: float) -> int:
    return max(0, min(255, int(round(_clamp01(value) * 255.0))))


def _sha(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def fabric_fields(size: int, seed: int, spec: FabricSpec = FabricSpec()) -> dict[str, tuple[int, bytes]]:
    if size < 16:
        raise ValueError("fabric texture size must be >=16")
    if spec.warp_threads < 2 or spec.weft_threads < 2:
        raise ValueError("fabric weave needs at least two warp/weft threads")
    height = [0.0] * (size * size)
    base = bytearray()
    rough = bytearray()
    ao = bytearray()
    thickness = bytearray()
    orm = bytearray()
    br, bg, bb = spec.base_rgb

    for y in range(size):
        v = (y + 0.5) / size
        for x in range(size):
            u = (x + 0.5) / size
            warp_phase = u * spec.warp_threads * math.pi
            weft_phase = v * spec.weft_threads * math.pi
            warp = 0.5 + 0.5 * math.cos(warp_phase)
            weft = 0.5 + 0.5 * math.cos(weft_phase)
            cell_x = int(u * spec.warp_threads)
            cell_y = int(v * spec.weft_threads)
            over = (cell_x + cell_y) & 1
            # Plain-weave signal: one thread family rises while the other passes below.
            weave = warp * (0.62 if over else 0.34) + weft * (0.34 if over else 0.62)
            fiber = fbm(u * 150.0, v * 150.0, seed + 101, octaves=3)
            macro = fbm(u * 5.0, v * 5.0, seed + 701)
            idx = y * size + x
            height[idx] = _clamp01(0.48 + (weave - 0.5) * spec.weave_depth + (fiber - 0.5) * spec.fiber_noise * 0.28)
            shade = 0.88 + macro * 0.16 + (fiber - 0.5) * 0.07
            tint = (weave - 0.5) * 0.055
            base.extend((
                max(0, min(255, round(br * shade * (1.0 + tint)))),
                max(0, min(255, round(bg * shade * (1.0 + tint * 0.8)))),
                max(0, min(255, round(bb * shade * (1.0 - tint * 0.5)))),
            ))
            roughness = spec.roughness + (fiber - 0.5) * 0.10 - (weave - 0.5) * 0.035
            rough_byte = _u8(roughness)
            rough.append(rough_byte)
            ao_value = _u8(0.84 + height[idx] * 0.15)
            ao.append(ao_value)
            thickness_value = _u8(_clamp01(0.62 + (macro - 0.5) * 0.14))
            thickness.append(thickness_value)
            orm.extend((ao_value, rough_byte, 0))

    normal = bytearray()
    height_bytes = bytearray(_u8(value) for value in height)
    for y in range(size):
        for x in range(size):
            left = height[y * size + max(0, x - 1)]
            right = height[y * size + min(size - 1, x + 1)]
            down = height[max(0, y - 1) * size + x]
            up = height[min(size - 1, y + 1) * size + x]
            dx = (right - left) * 5.5
            dy = (up - down) * 5.5
            nx, ny, nz = -dx, -dy, 1.0
            inv = 1.0 / math.sqrt(nx * nx + ny * ny + nz * nz)
            normal.extend((_u8(nx * inv * 0.5 + 0.5), _u8(ny * inv * 0.5 + 0.5), _u8(nz * inv * 0.5 + 0.5)))

    return {
        "base_color": (3, bytes(base)),
        "roughness": (1, bytes(rough)),
        "height": (1, bytes(height_bytes)),
        "normal": (3, bytes(normal)),
        "ao": (1, bytes(ao)),
        "thickness": (1, bytes(thickness)),
        "orm": (3, bytes(orm)),
    }


def write_fabric_material(output: str | Path, *, size: int = 256, seed: int = 1, spec: FabricSpec = FabricSpec()) -> dict[str, object]:
    root = Path(output)
    root.mkdir(parents=True, exist_ok=True)
    maps = {}
    for name, (channels, pixels) in fabric_fields(size, seed, spec).items():
        data = png_bytes(size, size, channels, pixels)
        filename = f"{name}.png"
        (root / filename).write_bytes(data)
        maps[name] = {"file": filename, "channels": channels, "sha256": _sha(data)}
    manifest = {
        "schema": "axm.game-assets.fabric-material.v0.1",
        "seed": seed,
        "maps": maps,
        "spec": {
            "base_rgb": list(spec.base_rgb),
            "warp_threads": spec.warp_threads,
            "weft_threads": spec.weft_threads,
            "weave_depth": spec.weave_depth,
            "roughness": spec.roughness,
            "fiber_noise": spec.fiber_noise,
            "thickness_hint_mm": spec.thickness_hint_mm,
        },
        "renderer_hints": {
            "metalness": 0.0,
            "two_sided": True,
            "roughness_source": "roughness.png",
            "normal_source": "normal.png",
            "thickness_source": "thickness.png",
        },
        "truth": {
            "physically_measured": False,
            "deterministic": True,
            "notes": [
                "Plain-weave and fiber detail are authored procedural signals, not microscopy or scan data.",
                "Thickness map is a material proxy and does not replace garment mesh thickness/collision state.",
                "High-end cloth still requires semantic seams, tailoring, wrinkle history and in-engine shading/motion evidence.",
            ],
        },
    }
    payload = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8")
    (root / "fabric-material.json").write_bytes(payload)
    manifest["manifest_sha256"] = _sha(payload)
    return manifest
