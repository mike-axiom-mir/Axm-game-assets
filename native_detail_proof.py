#!/usr/bin/env python3
"""End-to-end native detail progression proof for a Sentinel armor component."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from native_gltf import write_gltf
from native_hardsurface import sentinel_armor_plate, validate_detail_progression
from native_pbr import write_painted_metal
from native_uv import box_project, validate_uv

SCHEMA = "axm.game-assets.native-detail-proof.v0.1"


def _sha256(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def build_detail_proof(output: str | Path, *, texture_size: int = 128, seed: int = 6007) -> dict[str, Any]:
    root = Path(output)
    root.mkdir(parents=True, exist_ok=True)
    progression = validate_detail_progression()
    if progression["status"] != "pass":
        raise ValueError(f"detail progression failed: {progression}")

    levels = []
    for level in range(4):
        mesh, detail = sentinel_armor_plate(level)
        level_root = root / f"lod_source_detail_{level}"
        write_painted_metal(level_root / "textures", size=texture_size, seed=seed + level)
        uv = box_project(mesh)
        uv_report = validate_uv(mesh, uv)
        if uv_report["status"] != "pass":
            raise ValueError(f"detail level {level} UV failed: {uv_report}")
        delivery = write_gltf(mesh, uv, level_root)
        levels.append({
            "level": level,
            "semantic_features": list(detail.semantic_features),
            "components": detail.components,
            "source_vertices": detail.vertices,
            "triangles": detail.triangles,
            "uv": uv_report,
            "delivery": delivery,
            "truth": "Detail source progression, not runtime LOD. Higher levels add semantic geometry rather than simplification.",
        })

    manifest = {
        "schema": SCHEMA,
        "asset": "sentinel-armor-native-detail-proof",
        "blender_required": False,
        "levels": levels,
        "acceptance": {
            "triangle_growth": all(b["triangles"] > a["triangles"] for a, b in zip(levels, levels[1:])),
            "component_growth": all(b["components"] > a["components"] for a, b in zip(levels, levels[1:])),
            "all_uv_valid": all(level["uv"]["status"] == "pass" for level in levels),
            "all_gltf_structural_valid": all(level["delivery"]["validation"]["status"] == "pass" for level in levels),
        },
        "truth": {
            "high_end_character_claim": False,
            "scope": "one rigid Sentinel armor component",
            "known_limits": [
                "No visual engine screenshot receipt yet",
                "No curvature-aware wear bake yet",
                "No production retopology",
                "No attribute-preserving runtime LOD derivation from the detailed source",
                "Component shells intersect rather than boolean-union into one watertight shell"
            ]
        }
    }
    manifest_bytes = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode()
    (root / "detail-proof.json").write_bytes(manifest_bytes)
    manifest["manifest_sha256"] = _sha256(manifest_bytes)
    return manifest
