#!/usr/bin/env python3
"""Deterministic upper-eyelash micro-ribbon material.

Each lash is represented by its own tapered card. v0.2 darkens and densifies
the single-filament envelope after v0.1 real-engine evidence showed that partial
alpha over skin read reddish and too faint. Geometry fit remains a separate gate.
"""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path

from native_pbr import fbm, png_bytes

SCHEMA = "axm.game-assets.lash-ribbon-material.v0.2"


@dataclass(frozen=True, slots=True)
class LashMaterialSpec:
    root_rgb: tuple[int, int, int] = (8, 6, 5)
    tip_rgb: tuple[int, int, int] = (18, 12, 10)
    density: float = 0.95
    roughness: float = 0.52


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
        root_fade = _clamp01(v / 0.028)
        tip_fade = _clamp01((1.0 - v) / 0.22) ** 0.78
        length_envelope = root_fade * tip_fade
        for x in range(size):
            u = (x + 0.5) / size
            # Slightly broader than v0.1 so a ~0.5 mm card survives close-view
            # minification while still reaching transparent edges.
            across = max(0.0, math.sin(math.pi * u)) ** 1.28
            grain = 0.96 + (fbm(u * 8.0, v * 15.0, seed + 1711, octaves=2) - 0.5) * 0.08
            alpha = _clamp01(spec.density * across * length_envelope * grain)
            total_alpha += alpha
            maximum_alpha = max(maximum_alpha, alpha)
            above_010 += int(alpha >= 0.10)
            above_035 += int(alpha >= 0.35)

            color_noise = fbm(u * 7.0, v * 13.0, seed + 3721, octaves=2)
            t = _clamp01(v * 0.68 + (color_noise - 0.5) * 0.06)
            r = spec.root_rgb[0] * (1.0 - t) + spec.tip_rgb[0] * t
            g = spec.root_rgb[1] * (1.0 - t) + spec.tip_rgb[1] * t
            b = spec.root_rgb[2] * (1.0 - t) + spec.tip_rgb[2] * t
            rgba.extend((round(r), round(g), round(b), _u8(alpha)))
            alpha_map.append(_u8(alpha))
            local_rough = _clamp01(spec.roughness + (color_noise - 0.5) * 0.05)
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
            "v0_1_visual_repair": "darker_broader_higher_alpha_filament",
            "notes": [
                "v0.2 increases dark filament coverage after v0.1 alpha-over-skin read too faint/reddish in Godot.",
                "One micro-ribbon still represents one authored lash guide; root fit and final aesthetics remain separate gates."
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
