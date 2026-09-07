#!/usr/bin/env python3
"""AXM deterministic layered eye material authoring v0.1."""
from __future__ import annotations

import hashlib
import json
import math
import random
from dataclasses import dataclass
from pathlib import Path

from native_pbr import fbm, png_bytes


@dataclass(frozen=True, slots=True)
class IrisSpec:
    inner_rgb: tuple[int, int, int] = (87, 91, 61)
    outer_rgb: tuple[int, int, int] = (43, 58, 48)
    filament_rgb: tuple[int, int, int] = (139, 124, 72)
    roughness: float = 0.32


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def _u8(value: float) -> int:
    return max(0, min(255, int(round(_clamp01(value) * 255.0))))


def _sha(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _distance_to_segment(px: float, py: float, ax: float, ay: float, bx: float, by: float) -> float:
    vx, vy = bx - ax, by - ay
    wx, wy = px - ax, py - ay
    vv = vx * vx + vy * vy
    if vv <= 1e-12:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, (wx * vx + wy * vy) / vv))
    qx, qy = ax + t * vx, ay + t * vy
    return math.hypot(px - qx, py - qy)


def iris_fields(size: int, seed: int, spec: IrisSpec = IrisSpec()) -> dict[str, tuple[int, bytes]]:
    if size < 16:
        raise ValueError("iris texture size must be >=16")
    height = [0.0] * (size * size)
    base = bytearray()
    roughness = bytearray()
    mask = bytearray()
    inner = spec.inner_rgb
    outer = spec.outer_rgb
    filament = spec.filament_rgb
    for y in range(size):
        v = (y + 0.5) / size * 2.0 - 1.0
        for x in range(size):
            u = (x + 0.5) / size * 2.0 - 1.0
            r = math.sqrt(u * u + v * v)
            angle = math.atan2(v, u)
            inside = r <= 1.0
            idx = y * size + x
            if not inside:
                base.extend((0, 0, 0))
                roughness.append(255)
                mask.append(0)
                height[idx] = 0.5
                continue
            rn = _clamp01(r)
            angular = math.sin(angle * 44.0 + fbm((u + 1.0) * 5.0, (v + 1.0) * 5.0, seed + 101) * 7.0)
            radial = fbm((angle / (2.0 * math.pi) + 0.5) * 18.0, rn * 9.0, seed + 701)
            spokes = _clamp01(0.5 + angular * 0.28 + (radial - 0.5) * 0.60)
            limbal = _clamp01((rn - 0.78) / 0.22)
            pupil_falloff = _clamp01((rn - 0.18) / 0.18)
            t = _clamp01(rn * 0.78 + limbal * 0.22)
            rcol = inner[0] * (1.0 - t) + outer[0] * t
            gcol = inner[1] * (1.0 - t) + outer[1] * t
            bcol = inner[2] * (1.0 - t) + outer[2] * t
            filament_mix = spokes * (1.0 - limbal) * 0.36
            rcol = rcol * (1.0 - filament_mix) + filament[0] * filament_mix
            gcol = gcol * (1.0 - filament_mix) + filament[1] * filament_mix
            bcol = bcol * (1.0 - filament_mix) + filament[2] * filament_mix
            dark = 0.20 + pupil_falloff * 0.80
            dark *= 1.0 - limbal * 0.48
            base.extend((max(0, min(255, round(rcol * dark))), max(0, min(255, round(gcol * dark))), max(0, min(255, round(bcol * dark)))))
            height[idx] = _clamp01(0.50 + (spokes - 0.5) * 0.11 * (1.0 - limbal))
            roughness.append(_u8(spec.roughness + (radial - 0.5) * 0.07))
            mask.append(255)

    normal = bytearray()
    for y in range(size):
        for x in range(size):
            idx = y * size + x
            left = height[y * size + max(0, x - 1)]
            right = height[y * size + min(size - 1, x + 1)]
            down = height[max(0, y - 1) * size + x]
            up = height[min(size - 1, y + 1) * size + x]
            dx = (right - left) * 3.0
            dy = (up - down) * 3.0
            nx, ny, nz = -dx, -dy, 1.0
            inv = 1.0 / math.sqrt(nx * nx + ny * ny + nz * nz)
            normal.extend((_u8(nx * inv * 0.5 + 0.5), _u8(ny * inv * 0.5 + 0.5), _u8(nz * inv * 0.5 + 0.5)))
    return {
        "iris_base_color": (3, bytes(base)),
        "iris_roughness": (1, bytes(roughness)),
        "iris_normal": (3, bytes(normal)),
        "iris_mask": (1, bytes(mask)),
    }


def sclera_fields(size: int, seed: int) -> dict[str, tuple[int, bytes]]:
    if size < 16:
        raise ValueError("sclera texture size must be >=16")
    rng = random.Random(seed ^ 0xE7E)
    veins = []
    for _ in range(24):
        ax = rng.choice((rng.uniform(0.0, 0.12), rng.uniform(0.88, 1.0)))
        ay = rng.random()
        bx = rng.uniform(0.22, 0.78)
        by = _clamp01(ay + rng.uniform(-0.22, 0.22))
        veins.append((ax, ay, bx, by, rng.uniform(0.0015, 0.005), rng.uniform(0.15, 0.55)))
    base = bytearray()
    rough = bytearray()
    height = [0.0] * (size * size)
    for y in range(size):
        v = (y + 0.5) / size
        for x in range(size):
            u = (x + 0.5) / size
            macro = fbm(u * 6.0, v * 6.0, seed + 1301)
            vein = 0.0
            for ax, ay, bx, by, width, strength in veins:
                d = _distance_to_segment(u, v, ax, ay, bx, by)
                if d < width * 2.5:
                    vein = max(vein, (1.0 - d / (width * 2.5)) * strength)
            r = 228 + (macro - 0.5) * 12 - vein * 34
            g = 225 + (macro - 0.5) * 10 - vein * 72
            b = 216 + (macro - 0.5) * 9 - vein * 70
            base.extend((max(0, min(255, round(r))), max(0, min(255, round(g))), max(0, min(255, round(b)))))
            rough.append(_u8(0.38 + (macro - 0.5) * 0.08))
            height[y * size + x] = _clamp01(0.5 + vein * 0.05 + (macro - 0.5) * 0.025)
    normal = bytearray()
    for y in range(size):
        for x in range(size):
            idx = y * size + x
            left = height[y * size + max(0, x - 1)]
            right = height[y * size + min(size - 1, x + 1)]
            down = height[max(0, y - 1) * size + x]
            up = height[min(size - 1, y + 1) * size + x]
            nx, ny, nz = -(right - left) * 2.0, -(up - down) * 2.0, 1.0
            inv = 1.0 / math.sqrt(nx * nx + ny * ny + nz * nz)
            normal.extend((_u8(nx * inv * 0.5 + 0.5), _u8(ny * inv * 0.5 + 0.5), _u8(nz * inv * 0.5 + 0.5)))
    return {
        "sclera_base_color": (3, bytes(base)),
        "sclera_roughness": (1, bytes(rough)),
        "sclera_normal": (3, bytes(normal)),
    }


def write_eye_material(output: str | Path, *, size: int = 256, seed: int = 1, iris_spec: IrisSpec = IrisSpec()) -> dict[str, object]:
    root = Path(output)
    root.mkdir(parents=True, exist_ok=True)
    fields = {**iris_fields(size, seed, iris_spec), **sclera_fields(size, seed + 99)}
    maps = {}
    for name, (channels, pixels) in fields.items():
        data = png_bytes(size, size, channels, pixels)
        filename = f"{name}.png"
        (root / filename).write_bytes(data)
        maps[name] = {"file": filename, "channels": channels, "sha256": _sha(data)}
    manifest = {
        "schema": "axm.game-assets.eye-material.v0.1",
        "seed": seed,
        "maps": maps,
        "layers": {
            "sclera": {"metalness": 0.0, "roughness_source": "sclera_roughness.png"},
            "iris": {"metalness": 0.0, "roughness_source": "iris_roughness.png", "normal_source": "iris_normal.png"},
            "pupil": {"base_color": [0.005, 0.005, 0.005], "roughness": 0.24},
            "cornea": {
                "openpbr_transmission_weight_hint": 1.0,
                "specular_ior_hint": 1.376,
                "roughness_hint": 0.015,
                "interpretation": "Renderer starting points for a clear corneal layer; this generator does not measure optical tissue properties."
            }
        },
        "truth": {
            "physically_measured": False,
            "deterministic": True,
            "notes": [
                "Iris filaments and scleral veins are procedural authored signals.",
                "High-end eyes still require semantic UV placement, tear line/meniscus, eyelid contact, wetness and real engine refraction validation."
            ]
        }
    }
    payload = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8")
    (root / "eye-material.json").write_bytes(payload)
    manifest["manifest_sha256"] = _sha(payload)
    return manifest
