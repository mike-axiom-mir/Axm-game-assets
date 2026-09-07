#!/usr/bin/env python3
"""AXM deterministic organic skin surface authoring v0.1.

Produces inspectable skin-like texture channels plus OpenPBR/MaterialX-oriented
subsurface metadata. This is authored CG material state, not measured human skin.
"""
from __future__ import annotations

import hashlib
import json
import math
import random
from dataclasses import dataclass
from pathlib import Path

from native_pbr import fbm, png_bytes


@dataclass(frozen=True, slots=True)
class SkinMaterialSpec:
    base_rgb: tuple[int, int, int] = (183, 132, 108)
    undertone_rgb: tuple[int, int, int] = (154, 78, 69)
    roughness: float = 0.46
    oiliness: float = 0.18
    pore_strength: float = 0.42
    freckle_density: float = 0.035
    subsurface_weight_hint: float = 0.58
    specular_ior_hint: float = 1.4


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def _u8(value: float) -> int:
    return max(0, min(255, int(round(_clamp01(value) * 255.0))))


def _sha(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def skin_fields(size: int, seed: int, spec: SkinMaterialSpec = SkinMaterialSpec()) -> dict[str, tuple[int, bytes]]:
    if size < 16:
        raise ValueError("skin texture size must be >=16")
    rng = random.Random(seed ^ 0x51A1)
    freckles = [(rng.random(), rng.random(), rng.uniform(0.004, 0.018), rng.uniform(0.20, 0.65)) for _ in range(max(1, int(size * size * spec.freckle_density / 220.0)))]
    height = [0.0] * (size * size)
    subsurface = [0.0] * (size * size)
    thickness = [0.0] * (size * size)

    for y in range(size):
        v = (y + 0.5) / size
        for x in range(size):
            u = (x + 0.5) / size
            macro = fbm(u * 5.0, v * 5.0, seed + 101)
            pores = fbm(u * 92.0, v * 92.0, seed + 901)
            fine = fbm(u * 180.0, v * 180.0, seed + 1901, octaves=3)
            crease = fbm(u * 20.0, v * 7.0, seed + 2901)
            pore_delta = (pores - 0.5) * 0.18 * spec.pore_strength + (fine - 0.5) * 0.05 * spec.pore_strength
            crease_delta = min(0.0, crease - 0.44) * 0.12
            idx = y * size + x
            height[idx] = _clamp01(0.53 + pore_delta + crease_delta)
            subsurface[idx] = _clamp01(spec.subsurface_weight_hint * (0.82 + macro * 0.28))
            thickness[idx] = _clamp01(0.55 + (macro - 0.5) * 0.30 + (fbm(u * 2.0, v * 2.0, seed + 3901) - 0.5) * 0.20)

    base = bytearray()
    rough = bytearray()
    height_bytes = bytearray(_u8(value) for value in height)
    normal = bytearray()
    ao = bytearray()
    sss = bytearray(_u8(value) for value in subsurface)
    thick = bytearray(_u8(value) for value in thickness)
    orm = bytearray()
    br, bg, bb = spec.base_rgb
    ur, ug, ub = spec.undertone_rgb

    for y in range(size):
        v = (y + 0.5) / size
        for x in range(size):
            u = (x + 0.5) / size
            idx = y * size + x
            vascular = fbm(u * 11.0, v * 11.0, seed + 4901)
            macro = fbm(u * 4.0, v * 4.0, seed + 5901)
            undertone = _clamp01((vascular - 0.42) * 0.65 + (macro - 0.5) * 0.20)
            freckle = 0.0
            for fx, fy, radius, strength in freckles:
                dx, dy = u - fx, v - fy
                distance = math.sqrt(dx * dx + dy * dy)
                if distance < radius:
                    freckle = max(freckle, (1.0 - distance / radius) * strength)
            shade = 0.93 + (macro - 0.5) * 0.12
            r = (br * (1.0 - undertone) + ur * undertone) * shade * (1.0 - freckle * 0.28)
            g = (bg * (1.0 - undertone) + ug * undertone) * shade * (1.0 - freckle * 0.34)
            b = (bb * (1.0 - undertone) + ub * undertone) * shade * (1.0 - freckle * 0.38)
            base.extend((max(0, min(255, round(r))), max(0, min(255, round(g))), max(0, min(255, round(b)))))

            oil = fbm(u * 3.5, v * 3.5, seed + 6901)
            pore_rough = (height[idx] - 0.5) * 0.16
            roughness = spec.roughness + pore_rough - spec.oiliness * max(0.0, oil - 0.52) * 0.55
            rough_byte = _u8(roughness)
            rough.append(rough_byte)

            left = height[y * size + max(0, x - 1)]
            right = height[y * size + min(size - 1, x + 1)]
            down = height[max(0, y - 1) * size + x]
            up = height[min(size - 1, y + 1) * size + x]
            dx = (right - left) * 5.0
            dy = (up - down) * 5.0
            nx, ny, nz = -dx, -dy, 1.0
            inv = 1.0 / math.sqrt(nx * nx + ny * ny + nz * nz)
            normal.extend((_u8(nx * inv * 0.5 + 0.5), _u8(ny * inv * 0.5 + 0.5), _u8(nz * inv * 0.5 + 0.5)))

            ao_value = _u8(0.91 + (height[idx] - 0.5) * 0.12)
            ao.append(ao_value)
            orm.extend((ao_value, rough_byte, 0))

    return {
        "base_color": (3, bytes(base)),
        "roughness": (1, bytes(rough)),
        "height": (1, bytes(height_bytes)),
        "normal": (3, bytes(normal)),
        "ao": (1, bytes(ao)),
        "subsurface_mask": (1, bytes(sss)),
        "thickness": (1, bytes(thick)),
        "orm": (3, bytes(orm)),
    }


def write_skin_material(output: str | Path, *, size: int = 512, seed: int = 1, spec: SkinMaterialSpec = SkinMaterialSpec()) -> dict[str, object]:
    root = Path(output)
    root.mkdir(parents=True, exist_ok=True)
    fields = skin_fields(size, seed, spec)
    maps = {}
    for name, (channels, pixels) in fields.items():
        data = png_bytes(size, size, channels, pixels)
        filename = f"{name}.png"
        (root / filename).write_bytes(data)
        maps[name] = {"file": filename, "channels": channels, "sha256": _sha(data)}
    material = {
        "schema": "axm.game-assets.skin-material.v0.1",
        "kind": "procedural_organic_skin",
        "seed": seed,
        "size": [size, size],
        "maps": maps,
        "openpbr_hints": {
            "base_metalness": 0.0,
            "specular_ior": spec.specular_ior_hint,
            "subsurface_weight": spec.subsurface_weight_hint,
            "subsurface_color": [1.0, 0.42, 0.32],
            "subsurface_radius_relative": [1.0, 0.46, 0.22],
            "interpretation": "Authored renderer starting points aligned to OpenPBR-style subsurface concepts; not measured tissue parameters."
        },
        "truth": {
            "physically_measured": False,
            "human_scan": False,
            "deterministic": True,
            "tileable": False,
            "notes": [
                "Pore, freckle, vascular and roughness variation are procedural authored signals.",
                "Thickness is a proxy mask for renderer tuning, not geometry-derived physical thickness.",
                "High-end facial skin still requires semantic UV regions, pose/expression wrinkles and in-engine subsurface validation."
            ]
        }
    }
    payload = (json.dumps(material, indent=2, sort_keys=True) + "\n").encode("utf-8")
    (root / "skin-material.json").write_bytes(payload)
    material["manifest_sha256"] = _sha(payload)
    return material
