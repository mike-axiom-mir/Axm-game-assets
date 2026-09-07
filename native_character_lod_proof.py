#!/usr/bin/env python3
"""Structural proof route for attribute-aware skinned/morphed character LOD."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Sequence

from native_animation import AnimationClip
from native_attribute_lod import as_character_inputs, deformation_error, from_mesh, simplify, validate
from native_character_gltf import write_character_gltf
from native_geometry import Mesh
from native_morph import MorphTarget
from native_pbr import write_painted_metal
from native_skin import Skeleton, SkinWeights
from native_uv import UVMap, validate_uv

SCHEMA = "axm.game-assets.character-lod-proof.v0.1"


def _sha256(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def prove_character_lods(
    mesh: Mesh,
    uvmap: UVMap,
    skin: SkinWeights,
    morph_targets: Sequence[MorphTarget],
    bind_skeleton: Skeleton,
    posed_skeletons: Sequence[Skeleton],
    output: str | Path,
    *,
    resolutions: Sequence[tuple[int, int]] = ((10, 8), (6, 6), (4, 4)),
    max_deformation_error: float = 0.03,
    animations: Sequence[AnimationClip] = (),
    texture_size: int = 32,
) -> dict[str, object]:
    if not posed_skeletons:
        raise ValueError("LOD proof requires at least one posed skeleton")
    root = Path(output)
    root.mkdir(parents=True, exist_ok=True)
    source = from_mesh(mesh, uvmap, skin=skin, morph_targets=morph_targets)
    source_triangles = len(source.triangles)
    levels = []
    previous_triangles = source_triangles + 1

    for level_index, (spatial_resolution, uv_resolution) in enumerate(resolutions, 1):
        lod = simplify(source, spatial_resolution=spatial_resolution, uv_resolution=uv_resolution, normal_resolution=2)
        validation = validate(lod, joint_count=len(bind_skeleton.joints))
        lod_mesh, lod_uv, lod_skin, lod_morphs = as_character_inputs(lod)
        uv_validation = validate_uv(lod_mesh, lod_uv)
        errors = [deformation_error(source, lod, bind_skeleton, pose) for pose in posed_skeletons]
        max_error = max(error["max"] for error in errors)
        mean_error = sum(error["mean"] for error in errors) / len(errors)

        level_root = root / f"lod{level_index}"
        write_painted_metal(level_root / "textures", size=texture_size, seed=9000 + level_index)
        delivery = write_character_gltf(
            lod_mesh,
            lod_uv,
            bind_skeleton,
            lod_skin,
            lod_morphs,
            level_root,
            animations=animations,
        )
        levels.append({
            "lod": level_index,
            "spatial_resolution": spatial_resolution,
            "uv_resolution": uv_resolution,
            "vertices": len(lod.vertices),
            "triangles": len(lod.triangles),
            "triangle_ratio": len(lod.triangles) / source_triangles if source_triangles else 0.0,
            "attribute_validation": validation,
            "uv_validation": uv_validation,
            "deformation": {"poses": errors, "max": max_error, "mean": mean_error, "budget": max_deformation_error},
            "delivery": delivery,
            "passes": {
                "reduced": len(lod.triangles) < previous_triangles,
                "attributes": validation["status"] == "pass",
                "uv": uv_validation["status"] == "pass",
                "deformation": max_error <= max_deformation_error,
                "gltf": delivery["validation"]["status"] == "pass",
            },
        })
        previous_triangles = len(lod.triangles)

    acceptance = {
        "all_levels_reduce_monotonically": all(level["passes"]["reduced"] for level in levels),
        "all_attributes_valid": all(level["passes"]["attributes"] for level in levels),
        "all_uv_valid": all(level["passes"]["uv"] for level in levels),
        "all_deformation_within_budget": all(level["passes"]["deformation"] for level in levels),
        "all_gltf_structural_valid": all(level["passes"]["gltf"] for level in levels),
    }
    manifest = {
        "schema": SCHEMA,
        "asset": mesh.name,
        "source": {"expanded_vertices": len(source.vertices), "triangles": source_triangles, "morph_targets": len(source.morph_names)},
        "levels": levels,
        "acceptance": acceptance,
        "truth": {
            "status": "experimental_attribute_preserving_lod",
            "production_character_lod_claim": False,
            "notes": [
                "UV, four-slot skin influences and morph deltas are carried through the experimental reducer.",
                "Deformation error compares each reduced vertex with the average posed position of its source cluster members.",
                "Passing a synthetic fixture does not approve Sentinel or prove silhouette/material quality in game.",
                "Reducer is spatial clustering, not a mature QEM/meshoptimizer-quality production simplifier."
            ],
        },
    }
    manifest_bytes = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode()
    (root / "character-lod-proof.json").write_bytes(manifest_bytes)
    manifest["manifest_sha256"] = _sha256(manifest_bytes)
    return manifest
