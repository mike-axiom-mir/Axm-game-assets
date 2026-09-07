#!/usr/bin/env python3
"""AXM deterministic hair-card material authoring v0.2."""
from __future__ import annotations

import hashlib
import json
import math
import random
from dataclasses import dataclass
from pathlib import Path

from native_pbr import fbm, png_bytes


@dataclass(frozen=True, slots=True)
class HairMaterialSpec:
    root_rgb: tuple[int, int, int] = (54, 37, 28)
    tip_rgb: tuple[int, int, int] = (78, 56, 43)
    strand_count: int = 22
    roughness: float = 0.42
    alpha_cutoff_hint: float = 0.34


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def _u8(value: float) -> int:
    return max(0, min(255, int(round(_clamp01(value) * 255.0))))


def _sha(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def hair_card_fields(size: int, seed: int, spec: HairMaterialSpec = HairMaterialSpec()) -> dict[str, tuple[int, bytes]]:
    if size < 16:
        raise ValueError("hair card texture size must be >=16")
    if spec.strand_count < 1:
        raise ValueError("strand_count must be positive")
    rng = random.Random(seed ^ 0xA11A)
    strands = []
    for index in range(spec.strand_count):
        center = (index + 0.5) / spec.strand_count + rng.uniform(-0.018, 0.018)
        width = rng.uniform(0.007, 0.021)
        phase = rng.uniform(-math.pi, math.pi)
        wave = rng.uniform(0.006, 0.025)
        lean = rng.uniform(-0.04, 0.04)
        strength = rng.uniform(0.70, 1.0)
        strands.append((center, width, phase, wave, lean, strength))

    rgba = bytearray()
    alpha_map = bytearray()
    rough = bytearray()
    orm = bytearray()
    root = spec.root_rgb
    tip = spec.tip_rgb
    for y in range(size):
        v = (y + 0.5) / size
        taper = _clamp01((1.0 - v) * 1.08)
        for x in range(size):
            u = (x + 0.5) / size
            alpha = 0.0
            strand_light = 0.0
            for center, width, phase, wave, lean, strength in strands:
                curve = center + lean * v + math.sin(v * math.pi * 2.2 + phase) * wave
                local_width = width * (0.28 + taper * 0.72)
                d = abs(u - curve)
                if d < local_width:
                    a = (1.0 - d / local_width) ** 1.7 * strength
                    if a > alpha:
                        alpha = a
                        strand_light = 1.0 - d / local_width
            edge_fade = _clamp01(min(u, 1.0 - u) * 18.0)
            alpha *= edge_fade
            noise = fbm(u * 28.0, v * 18.0, seed + 1701, octaves=3)
            t = _clamp01(v * 0.86 + (noise - 0.5) * 0.14)
            r = root[0] * (1.0 - t) + tip[0] * t
            g = root[1] * (1.0 - t) + tip[1] * t
            b = root[2] * (1.0 - t) + tip[2] * t
            highlight = 0.90 + strand_light * 0.14
            rgba.extend((
                max(0, min(255, round(r * highlight))),
                max(0, min(255, round(g * highlight))),
                max(0, min(255, round(b * highlight))),
                _u8(alpha),
            ))
            alpha_map.append(_u8(alpha))
            roughness = spec.roughness + (noise - 0.5) * 0.08 - strand_light * 0.035
            rough_byte = _u8(roughness)
            rough.append(rough_byte)
            # glTF metallic-roughness packing: R can serve occlusion, G roughness, B metallic.
            orm.extend((255, rough_byte, 0))
    return {
        "base_color_alpha": (4, bytes(rgba)),
        "alpha": (1, bytes(alpha_map)),
        "roughness": (1, bytes(rough)),
        "orm": (3, bytes(orm)),
    }


def write_hair_material(output: str | Path, *, size: int = 256, seed: int = 1, spec: HairMaterialSpec = HairMaterialSpec()) -> dict[str, object]:
    root = Path(output)
    root.mkdir(parents=True, exist_ok=True)
    maps = {}
    for name, (channels, pixels) in hair_card_fields(size, seed, spec).items():
        data = png_bytes(size, size, channels, pixels)
        filename = f"{name}.png"
        (root / filename).write_bytes(data)
        maps[name] = {"file": filename, "channels": channels, "sha256": _sha(data)}
    manifest = {
        "schema": "axm.game-assets.hair-card-material.v0.2",
        "seed": seed,
        "maps": maps,
        "renderer_hints": {
            "two_sided": True,
            "alpha_mode": "MASK_OR_BLEND",
            "alpha_cutoff": spec.alpha_cutoff_hint,
            "metalness": 0.0,
            "roughness_source": "roughness.png",
            "metallic_roughness_source": "orm.png",
            "anisotropic_specular": "recommended when target renderer supports it",
        },
        "truth": {
            "physically_measured": False,
            "deterministic": True,
            "notes": [
                "Texture represents grouped hair strands on a card, not individual fiber geometry.",
                "ORM packs occlusion=1, generated roughness, metallic=0 for runtime delivery.",
                "Card orientation, scalp coverage, sorting/alpha artifacts and motion require separate visual/in-engine gates.",
            ],
        },
    }
    payload = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8")
    (root / "hair-material.json").write_bytes(payload)
    manifest["manifest_sha256"] = _sha(payload)
    return manifest
