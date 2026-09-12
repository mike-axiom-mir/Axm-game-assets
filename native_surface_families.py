#!/usr/bin/env python3
"""Deterministic multi-family surface authoring for AXM Game Asset Forge.

The family vocabulary and several signal formulas are adapted from the finished
Universal Creation RTS/workshop surface donor at commit
a5cc708457b7e8f33e794fdac648ae65d15a0fb4, especially
tools/blender/axm_salvage_surfaces.py. This is a native stdlib-only Forge port:
it does not import Universal Creation, Blender, NumPy, Pillow, or network code.

These maps are authored procedural material signals, not measured scans and not
an aesthetic/AAA/PBR certification.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any

from native_pbr import fbm, png_bytes

SCHEMA = "axm.game-assets.native-surface-family/v0.1"
DONOR = {
    "repo": "mike-axiom-mir/axm-universal-creation",
    "commit": "a5cc708457b7e8f33e794fdac648ae65d15a0fb4",
    "mechanism": "tools/blender/axm_salvage_surfaces.py",
}
KINDS = ("salvage_metal", "steel", "wood", "cloth", "stone", "soil", "rubber")


@dataclass(frozen=True, slots=True)
class SurfaceFamilySpec:
    kind: str
    base_rgb: tuple[int, int, int]
    roughness: float
    metallic: float
    relief_strength: float = 3.0
    scale: float = 1.0


DEFAULT_SPECS: dict[str, SurfaceFamilySpec] = {
    "salvage_metal": SurfaceFamilySpec("salvage_metal", (54, 92, 96), 0.59, 0.70, 3.4, 1.0),
    "steel": SurfaceFamilySpec("steel", (174, 182, 173), 0.42, 0.90, 2.2, 1.0),
    "wood": SurfaceFamilySpec("wood", (142, 107, 68), 0.84, 0.0, 2.6, 1.0),
    "cloth": SurfaceFamilySpec("cloth", (56, 108, 124), 0.92, 0.0, 2.0, 1.0),
    "stone": SurfaceFamilySpec("stone", (146, 144, 131), 0.90, 0.0, 2.8, 1.0),
    "soil": SurfaceFamilySpec("soil", (80, 65, 53), 0.96, 0.0, 2.5, 1.0),
    "rubber": SurfaceFamilySpec("rubber", (36, 44, 48), 0.82, 0.0, 3.2, 1.0),
}


def _clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, value))


def _u8(value: float) -> int:
    return max(0, min(255, round(_clamp(value) * 255.0)))


def _sha256(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _rgb01(rgb: tuple[int, int, int]) -> tuple[float, float, float]:
    if len(rgb) != 3 or any(type(value) is not int or value < 0 or value > 255 for value in rgb):
        raise ValueError("base_rgb must contain three integers within [0,255]")
    return tuple(value / 255.0 for value in rgb)


def _hash01(x: int, y: int, seed: int) -> float:
    payload = f"{seed}:{x}:{y}".encode("utf-8")
    return int.from_bytes(hashlib.sha256(payload).digest()[:8], "big") / (2**64 - 1)


def _signals(size: int, seed: int, spec: SurfaceFamilySpec) -> dict[str, list[float] | list[tuple[float, float, float]]]:
    if spec.kind not in KINDS:
        raise ValueError(f"unsupported surface kind {spec.kind!r}")
    if size < 8:
        raise ValueError("size must be >= 8")
    if not math.isfinite(spec.relief_strength) or spec.relief_strength < 0.0:
        raise ValueError("relief_strength must be finite and non-negative")
    if not math.isfinite(spec.scale) or spec.scale <= 0.0:
        raise ValueError("scale must be finite and positive")
    base_rgb = _rgb01(spec.base_rgb)
    base: list[tuple[float, float, float]] = []
    rough: list[float] = []
    metal: list[float] = []
    height: list[float] = []
    ao: list[float] = []

    for y in range(size):
        v = (y + 0.5) / size
        for x in range(size):
            u = (x + 0.5) / size
            s = spec.scale
            broad = fbm(u * 5.0 * s, v * 5.0 * s, seed + 101)
            mid = fbm(u * 31.0 * s, v * 31.0 * s, seed + 503)
            fine = fbm(u * 137.0 * s, v * 137.0 * s, seed + 907, octaves=4)
            grain = _hash01(x, y, seed + 1601)

            rr, gg, bb = base_rgb
            rgh = spec.roughness
            met = spec.metallic
            h = 0.5
            occlusion = 0.96

            if spec.kind == "salvage_metal":
                field = 0.51 * broad + 0.37 * mid + 0.12 * fine
                chip = _clamp((field - 0.67) * 16.0)
                halo = _clamp((field - 0.63) * 13.0)
                rust = (
                    0.16 + 0.13 * mid,
                    0.066 + 0.045 * fine,
                    0.028 + 0.020 * fine,
                )
                shade = 0.78 + 0.23 * broad + 0.07 * fine
                rr, gg, bb = (component * shade * (1.0 - 0.38 * halo) for component in base_rgb)
                rr = rr * (1.0 - chip) + rust[0] * chip
                gg = gg * (1.0 - chip) + rust[1] * chip
                bb = bb * (1.0 - chip) + rust[2] * chip
                scratch = 1.0 if grain > 0.997 and mid > 0.44 else 0.0
                if scratch:
                    rr, gg, bb = 0.49, 0.47, 0.39
                rgh = 0.43 + 0.27 * chip + 0.15 * mid
                met = 0.72 * (1.0 - chip) + 0.20 * chip
                h = 0.53 + 0.08 * (fine - 0.5) - 0.16 * chip - 0.06 * scratch
                occlusion = 0.84 + 0.16 * _clamp(h)
            elif spec.kind == "steel":
                brushed = math.sin(v * math.tau * 115.0 * s) ** 2
                shade = 0.79 + 0.17 * brushed + 0.11 * mid
                rr, gg, bb = (component * shade for component in base_rgb)
                rgh = 0.28 + 0.25 * mid
                met = 0.90
                h = 0.50 + 0.03 * (fine - 0.5) + 0.012 * (brushed - 0.5)
                occlusion = 0.94 + 0.06 * broad
            elif spec.kind == "wood":
                rings = 0.5 + 0.5 * math.sin(
                    (u + 0.019 * math.sin(v * 11.0) + 0.008 * broad) * 180.0 * s
                )
                shade = 0.74 + 0.18 * rings + 0.15 * mid
                rr, gg, bb = (component * shade for component in base_rgb)
                crack = 1.0 if rings < 0.018 and broad > 0.58 else 0.0
                if crack:
                    rr, gg, bb = rr * 0.42, gg * 0.42, bb * 0.42
                rgh = 0.75 + 0.20 * fine
                met = 0.0
                h = 0.50 + 0.07 * (rings - 0.5) + 0.045 * (mid - 0.5) - 0.08 * crack
                occlusion = 0.83 + 0.17 * _clamp(h)
            elif spec.kind == "cloth":
                weave = 0.5 + 0.5 * (
                    math.sin(u * math.tau * 105.0 * s) * math.sin(v * math.tau * 105.0 * s)
                )
                stain = _clamp((broad - 0.55) * 6.0)
                shade = (0.78 + 0.15 * weave + 0.20 * mid) * (1.0 - 0.19 * stain)
                rr, gg, bb = (component * shade for component in base_rgb)
                rgh = 0.88 + 0.10 * mid
                met = 0.0
                h = 0.50 + 0.055 * (weave - 0.5) + 0.025 * (fine - 0.5)
                occlusion = 0.90 + 0.10 * _clamp(h)
            elif spec.kind in {"stone", "soil"}:
                shade = 0.80 + 0.20 * mid + 0.055 * grain
                if spec.kind == "soil":
                    shade *= 0.91 + 0.10 * broad
                rr, gg, bb = (component * shade for component in base_rgb)
                rgh = 0.82 + 0.15 * fine if spec.kind == "stone" else 0.90 + 0.08 * fine
                met = 0.0
                h = 0.50 + 0.075 * (mid - 0.5) + 0.025 * (fine - 0.5)
                occlusion = 0.80 + 0.20 * _clamp(h)
            elif spec.kind == "rubber":
                shade = 0.72 + 0.24 * fine + 0.08 * mid
                rr, gg, bb = (component * shade for component in base_rgb)
                rgh = 0.72 + 0.20 * mid
                met = 0.0
                h = 0.50 + 0.075 * (fine - 0.5) + 0.02 * (grain - 0.5)
                occlusion = 0.88 + 0.12 * _clamp(h)

            base.append((_clamp(rr), _clamp(gg), _clamp(bb)))
            rough.append(_clamp(rgh))
            metal.append(_clamp(met))
            height.append(_clamp(h))
            ao.append(_clamp(occlusion))

    return {"base": base, "roughness": rough, "metallic": metal, "height": height, "ao": ao}


def _normal_map(height: list[float], size: int, strength: float) -> list[tuple[float, float, float]]:
    out: list[tuple[float, float, float]] = []
    for y in range(size):
        for x in range(size):
            left = height[y * size + max(0, x - 1)]
            right = height[y * size + min(size - 1, x + 1)]
            down = height[max(0, y - 1) * size + x]
            up = height[min(size - 1, y + 1) * size + x]
            dx = (right - left) * strength
            dy = (up - down) * strength
            nx, ny, nz = -dx, -dy, 1.0
            inv = 1.0 / math.sqrt(nx * nx + ny * ny + nz * nz)
            out.append((nx * inv * 0.5 + 0.5, ny * inv * 0.5 + 0.5, nz * inv * 0.5 + 0.5))
    return out


def build_surface_family(
    *,
    size: int = 256,
    seed: int = 1,
    spec: SurfaceFamilySpec,
) -> dict[str, tuple[int, bytes]]:
    signal = _signals(size, seed, spec)
    base = bytearray()
    rough = bytearray()
    metal = bytearray()
    height = bytearray()
    ao = bytearray()
    orm = bytearray()
    for rgb, rgh, met, h, occ in zip(
        signal["base"],
        signal["roughness"],
        signal["metallic"],
        signal["height"],
        signal["ao"],
    ):
        base.extend(_u8(value) for value in rgb)
        rough.append(_u8(rgh))
        metal.append(_u8(met))
        height.append(_u8(h))
        ao.append(_u8(occ))
        orm.extend((_u8(occ), _u8(rgh), _u8(met)))
    normal = bytearray()
    for rgb in _normal_map(signal["height"], size, spec.relief_strength):
        normal.extend(_u8(value) for value in rgb)
    return {
        "base_color": (3, bytes(base)),
        "roughness": (1, bytes(rough)),
        "metallic": (1, bytes(metal)),
        "height": (1, bytes(height)),
        "normal": (3, bytes(normal)),
        "ao": (1, bytes(ao)),
        "orm": (3, bytes(orm)),
    }


def write_surface_family(
    output: str | Path,
    *,
    kind: str,
    size: int = 256,
    seed: int = 1,
    name: str | None = None,
    base_rgb: tuple[int, int, int] | None = None,
    relief_strength: float | None = None,
    scale: float | None = None,
) -> dict[str, Any]:
    if kind not in DEFAULT_SPECS:
        raise ValueError(f"unknown surface family {kind!r}; choose from {', '.join(KINDS)}")
    spec = DEFAULT_SPECS[kind]
    if base_rgb is not None:
        spec = replace(spec, base_rgb=base_rgb)
    if relief_strength is not None:
        spec = replace(spec, relief_strength=float(relief_strength))
    if scale is not None:
        spec = replace(spec, scale=float(scale))
    root = Path(output)
    root.mkdir(parents=True, exist_ok=True)
    if any(root.iterdir()):
        raise FileExistsError(f"surface output must start empty: {root}")
    fields = build_surface_family(size=size, seed=seed, spec=spec)
    maps: dict[str, dict[str, Any]] = {}
    for map_id, (channels, pixels) in fields.items():
        payload = png_bytes(size, size, channels, pixels)
        file_name = f"{map_id}.png"
        (root / file_name).write_bytes(payload)
        maps[map_id] = {
            "file": file_name,
            "sha256": _sha256(payload),
            "bytes": len(payload),
            "channels": channels,
        }
    manifest: dict[str, Any] = {
        "schema": SCHEMA,
        "family_id": name or f"{kind}-{seed}",
        "kind": kind,
        "seed": seed,
        "size": [size, size],
        "spec": {
            **asdict(spec),
            "base_rgb": list(spec.base_rgb),
        },
        "maps": maps,
        "packed_map_truth": {
            "orm": {
                "r": "ambient-occlusion",
                "g": "roughness",
                "b": "metallic",
                "note": "Packed delivery view; individual source maps are also materialized.",
            }
        },
        "provenance": {
            "donor": DONOR,
            "implementation": "AXM Game Asset Forge stdlib-only native adaptation",
        },
        "truth": {
            "deterministic": True,
            "physically_measured": False,
            "source_picture_projection": False,
            "aesthetic_quality_proven": False,
            "physical_pbr_certified": False,
            "automatic_genome_mutation": False,
            "notes": [
                "Procedural surface signals are authored, not measured scans.",
                "Relief normal is derived from generated height; no displacement claim.",
                "Material-family identity is explicit and never inferred from a filename.",
            ],
        },
    }
    core_digest = _sha256(_canonical(manifest))
    manifest["manifest_digest"] = core_digest
    (root / "material-family.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate one deterministic native Forge surface family")
    parser.add_argument("output", type=Path)
    parser.add_argument("--kind", choices=KINDS, required=True)
    parser.add_argument("--size", type=int, default=256)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--name")
    args = parser.parse_args(argv)
    manifest = write_surface_family(
        args.output,
        kind=args.kind,
        size=args.size,
        seed=args.seed,
        name=args.name,
    )
    print(json.dumps({
        "schema": manifest["schema"],
        "family_id": manifest["family_id"],
        "kind": manifest["kind"],
        "manifest_digest": manifest["manifest_digest"],
        "maps": len(manifest["maps"]),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
