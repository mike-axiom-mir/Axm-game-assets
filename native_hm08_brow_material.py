#!/usr/bin/env python3
"""Deterministic soft-density eyebrow card material for close human faces.

Generic scalp-hair cards intentionally leave most texels transparent around
individual strand clusters. At eyebrow scale that sparse alpha minifies into
on/off dots. This organ keeps longitudinal filament variation but authors a
continuous soft density envelope so overlapping source-grounded brow cards can
survive close-view rasterization without becoming painted skin texture.
"""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path

from native_pbr import fbm, png_bytes

SCHEMA = "axm.game-assets.brow-density-material.v0.1"


@dataclass(frozen=True, slots=True)
class BrowMaterialSpec:
    root_rgb: tuple[int, int, int] = (28, 20, 17)
    tip_rgb: tuple[int, int, int] = (44, 31, 25)
    density: float = 0.58
    roughness: float = 0.58
    filament_contrast: float = 0.18


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def _u8(value: float) -> int:
    return max(0, min(255, round(_clamp01(value) * 255.0)))


def _sha(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def brow_card_fields(
    size: int,
    seed: int,
    spec: BrowMaterialSpec = BrowMaterialSpec(),
) -> tuple[dict[str, tuple[int, bytes]], dict[str, float]]:
    if size < 16:
        raise ValueError("brow card texture size must be >=16")
    if not (0.05 <= spec.density <= 1.0):
        raise ValueError("brow density must be within [0.05,1]")
    if not (0.0 <= spec.roughness <= 1.0):
        raise ValueError("brow roughness must be within [0,1]")
    if not (0.0 <= spec.filament_contrast <= 0.5):
        raise ValueError("brow filament contrast must be within [0,0.5]")

    rgba = bytearray()
    alpha_map = bytearray()
    rough = bytearray()
    orm = bytearray()
    alpha_sum = 0.0
    alpha_max = 0.0
    above_010 = 0
    above_025 = 0

    for y in range(size):
        v = (y + 0.5) / size
        # Fade only the first/last few percent along the guide. Unlike the
        # generic hair-card texture, the interior remains a continuous density
        # field instead of isolated transparent strand islands.
        root_fade = _clamp01(v / 0.055)
        tip_fade = _clamp01((1.0 - v) / 0.16) ** 0.62
        length_envelope = root_fade * tip_fade
        phase = math.sin(v * math.tau * 1.7 + seed * 0.0017) * 0.55
        for x in range(size):
            u = (x + 0.5) / size
            # Rounded card cross-section, zero at the outer edges so cards can
            # overlap without revealing rectangular silhouettes.
            across = max(0.0, math.sin(math.pi * u)) ** 0.72
            filament = 0.5 + 0.5 * math.cos(u * math.tau * 10.0 + phase)
            filament_gain = 1.0 - spec.filament_contrast + spec.filament_contrast * filament
            grain = 0.90 + (fbm(u * 16.0, v * 11.0, seed + 6203, octaves=3) - 0.5) * 0.20
            alpha = _clamp01(spec.density * across * length_envelope * filament_gain * grain)
            alpha_sum += alpha
            alpha_max = max(alpha_max, alpha)
            above_010 += int(alpha >= 0.10)
            above_025 += int(alpha >= 0.25)

            color_noise = fbm(u * 9.0, v * 13.0, seed + 911, octaves=2)
            t = _clamp01(v * 0.72 + (color_noise - 0.5) * 0.10)
            r = spec.root_rgb[0] * (1.0 - t) + spec.tip_rgb[0] * t
            g = spec.root_rgb[1] * (1.0 - t) + spec.tip_rgb[1] * t
            b = spec.root_rgb[2] * (1.0 - t) + spec.tip_rgb[2] * t
            # Very small filament lift keeps directional structure visible
            # without punching holes through the alpha field.
            lift = 0.94 + filament * 0.08
            rgba.extend((
                max(0, min(255, round(r * lift))),
                max(0, min(255, round(g * lift))),
                max(0, min(255, round(b * lift))),
                _u8(alpha),
            ))
            alpha_map.append(_u8(alpha))
            local_rough = _clamp01(spec.roughness + (color_noise - 0.5) * 0.07 - filament * 0.025)
            rough_byte = _u8(local_rough)
            rough.append(rough_byte)
            orm.extend((255, rough_byte, 0))

    pixels = size * size
    evidence = {
        "mean_alpha": alpha_sum / pixels,
        "max_alpha": alpha_max,
        "fraction_alpha_ge_0_10": above_010 / pixels,
        "fraction_alpha_ge_0_25": above_025 / pixels,
    }
    fields = {
        "base_color_alpha": (4, bytes(rgba)),
        "alpha": (1, bytes(alpha_map)),
        "roughness": (1, bytes(rough)),
        "orm": (3, bytes(orm)),
    }
    return fields, evidence


def write_brow_material(
    output: str | Path,
    *,
    size: int = 256,
    seed: int = 1,
    spec: BrowMaterialSpec = BrowMaterialSpec(),
) -> dict[str, object]:
    root = Path(output)
    root.mkdir(parents=True, exist_ok=True)
    fields, evidence = brow_card_fields(size, seed, spec)
    maps: dict[str, dict[str, object]] = {}
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
        "renderer_hints": {
            "two_sided": True,
            "alpha_mode": "BLEND",
            "metalness": 0.0,
            "roughness_source": "roughness.png",
            "metallic_roughness_source": "orm.png",
        },
        "truth": {
            "physically_measured": False,
            "deterministic": True,
            "preferred_brow_claim": False,
            "notes": [
                "This is an authored eyebrow density field, not measured human fiber data.",
                "Continuous card alpha is intentional to survive close-view minification; filament variation modulates density without large transparent gaps.",
                "Geometry placement, card overlap and final brow aesthetics remain separate real-engine evidence gates.",
            ],
        },
    }
    payload = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8")
    (root / "brow-material.json").write_bytes(payload)
    manifest["manifest_sha256"] = _sha(payload)
    return manifest


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("output", nargs="?", default="build/brow-material")
    parser.add_argument("--size", type=int, default=128)
    parser.add_argument("--seed", type=int, default=52081)
    args = parser.parse_args()
    result = write_brow_material(args.output, size=args.size, seed=args.seed)
    print(json.dumps(result["coverage_evidence"], indent=2, sort_keys=True))
