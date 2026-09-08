#!/usr/bin/env python3
"""Deterministic upper-eyelash micro-ribbon material.

Each lash is already represented by its own tapered card, so the texture should
not contain a sparse bundle of many unrelated fibers. It supplies one soft dark
filament envelope across the card width and fades along the tip, preserving
subpixel coverage under alpha blending.
"""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path

from native_pbr import fbm, png_bytes

SCHEMA = "axm.game-assets.lash-ribbon-material.v0.1"


@dataclass(frozen=True, slots=True)
class LashMaterialSpec:
    root_rgb: tuple[int, int, int] = (17, 12, 10)
    tip_rgb: tuple[int, int, int] = (29, 20, 16)
    density: float = 0.78
    roughness: float = 0.54


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def _u8(value: float) -> int:
    return max(0, min(255, round(_clamp01(value) * 255.0)))


def _sha(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def lash_ribbon_fields(
    size: int,
    seed: int,
    spec: LashMaterialSpec = LashMaterialSpec(),
) -> tuple[dict[str, tuple[int, bytes]], dict[str, float]]:
    if size < 16:
        raise ValueError("lash texture size must be >=16")
    if not (0.10 <= spec.density <= 1.0):
        raise ValueError("lash density must be within [0.10,1]")

    rgba = bytearray()
    alpha_map = bytearray()
    rough = bytearray()
    orm = bytearray()
    total_alpha = 0.0
    maximum_alpha = 0.0
    above_010 = 0
    above_035 = 0

    for y in range(size):
        v = (y + 0.5) / size
        root_fade = _clamp01(v / 0.035)
        tip_fade = _clamp01((1.0 - v) / 0.24) ** 0.82
        length_envelope = root_fade * tip_fade
        for x in range(size):
            u = (x + 0.5) / size
            # One soft tapered filament. A broad center survives minification;
            # the outer edge still reaches zero so the ribbon boundary is hidden.
            across = max(0.0, math.sin(math.pi * u)) ** 1.55
            grain = 0.94 + (fbm(u * 9.0, v * 16.0, seed + 1711, octaves=2) - 0.5) * 0.10
            alpha = _clamp01(spec.density * across * length_envelope * grain)
            total_alpha += alpha
            maximum_alpha = max(maximum_alpha, alpha)
            above_010 += int(alpha >= 0.10)
            above_035 += int(alpha >= 0.35)

            color_noise = fbm(u * 7.0, v * 13.0, seed + 3721, octaves=2)
            t = _clamp01(v * 0.72 + (color_noise - 0.5) * 0.07)
            r = spec.root_rgb[0] * (1.0 - t) + spec.tip_rgb[0] * t
            g = spec.root_rgb[1] * (1.0 - t) + spec.tip_rgb[1] * t
            b = spec.root_rgb[2] * (1.0 - t) + spec.tip_rgb[2] * t
            rgba.extend((round(r), round(g), round(b), _u8(alpha)))
            alpha_map.append(_u8(alpha))
            local_rough = _clamp01(spec.roughness + (color_noise - 0.5) * 0.06)
            rough_byte = _u8(local_rough)
            rough.append(rough_byte)
            orm.extend((255, rough_byte, 0))

    pixels = size * size
    evidence = {
        "mean_alpha": total_alpha / pixels,
        "max_alpha": maximum_alpha,
        "fraction_alpha_ge_0_10": above_010 / pixels,
        "fraction_alpha_ge_0_35": above_035 / pixels,
    }
    return {
        "base_color_alpha": (4, bytes(rgba)),
        "alpha": (1, bytes(alpha_map)),
        "roughness": (1, bytes(rough)),
        "orm": (3, bytes(orm)),
    }, evidence


def write_lash_material(
    output: str | Path,
    *,
    size: int = 128,
    seed: int = 1,
    spec: LashMaterialSpec = LashMaterialSpec(),
) -> dict[str, object]:
    root = Path(output)
    root.mkdir(parents=True, exist_ok=True)
    fields, evidence = lash_ribbon_fields(size, seed, spec)
    maps = {}
    for name, (channels, pixels) in fields.items():
        data = png_bytes(size, size, channels, pixels)
        filename = f"{name}.png"
        (root / filename).write_bytes(data)
        maps[name] = {"file": filename, "channels": channels, "sha256": _sha(data)}
    manifest: dict[str, object] = {
        "schema": SCHEMA,
        "seed": seed,
        "size": [size, size],
        "maps": maps,
        "coverage_evidence": evidence,
        "renderer_hints": {"two_sided": True, "alpha_mode": "BLEND", "metalness": 0.0},
        "truth": {
            "physically_measured": False,
            "deterministic": True,
            "preferred_lash_claim": False,
            "notes": [
                "One micro-ribbon represents one authored lash guide, so the alpha field contains one soft filament rather than a scalp-hair bundle.",
                "Root fit and visible eyelid contact require separate geometry and Godot evidence gates.",
            ],
        },
    }
    payload = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8")
    (root / "lash-material.json").write_bytes(payload)
    manifest["manifest_sha256"] = _sha(payload)
    return manifest


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("output", nargs="?", default="build/lash-material")
    parser.add_argument("--size", type=int, default=128)
    parser.add_argument("--seed", type=int, default=62081)
    args = parser.parse_args()
    result = write_lash_material(args.output, size=args.size, seed=args.seed)
    print(json.dumps(result["coverage_evidence"], indent=2, sort_keys=True))
