#!/usr/bin/env python3
"""AXM recessed-receiver Sentinel four-material package v0.1.

Parallel evidence package. It deliberately does not replace the preferred
non-recessed multi-material route until real engine A/B evidence approves it.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from native_geometry import Mesh, triangulate
from native_multi_gltf import MaterialPrimitive, write_multi_gltf
from native_pbr import write_painted_metal
from native_uv import box_project_world, validate_uv
from native_weapon_multimat import (
    DEFAULT_WORLD_UNITS_PER_TILE,
    GROUP_ORDER,
    _material_specs,
    semantic_material_groups,
)
from native_weapon_recess_variant import (
    receiver_recess_variant_report,
    sentinel_rifle_recessed,
)

SCHEMA = "axm.game-assets.weapon-recess-multimat.v0.1"


def build_recessed_weapon_multimat_package(
    output: str | Path,
    *,
    texture_size: int = 128,
    seed: int = 8801,
    world_units_per_tile: float = DEFAULT_WORLD_UNITS_PER_TILE,
) -> dict[str, object]:
    root = Path(output)
    root.mkdir(parents=True, exist_ok=True)
    asset = sentinel_rifle_recessed()
    recess_state = receiver_recess_variant_report(asset)
    if recess_state["status"] != "pass":
        raise ValueError(f"recess variant invalid before material packaging: {recess_state}")

    groups = semantic_material_groups(asset)
    specs = _material_specs()
    primitives: list[MaterialPrimitive] = []
    group_receipts: dict[str, object] = {}
    grouped_triangles = 0

    for group_index, group in enumerate(GROUP_ORDER):
        group_mesh = groups[group]["mesh"]
        assert isinstance(group_mesh, Mesh)
        uv = box_project_world(
            group_mesh,
            world_units_per_tile=world_units_per_tile,
            origin=(0.0, 0.0, 0.0),
        )
        uv_report = validate_uv(group_mesh, uv)
        if uv_report["status"] != "pass":
            raise ValueError(f"{group} UV failed for recessed package: {uv_report}")
        spec_record = specs[group]
        material = write_painted_metal(
            root / "textures" / group,
            size=texture_size,
            seed=seed + group_index * 1009,
            spec=spec_record["spec"],
        )
        primitives.append(
            MaterialPrimitive(
                group_mesh,
                uv,
                str(spec_record["name"]),
                f"textures/{group}/base_color.png",
                f"textures/{group}/normal.png",
                f"textures/{group}/orm.png",
                metallic_factor=float(spec_record["metallic_factor"]),
            )
        )
        triangles = int(groups[group]["triangles"])
        grouped_triangles += triangles
        group_receipts[group] = {
            "material_name": spec_record["name"],
            "components": groups[group]["components"],
            "component_count": len(groups[group]["components"]),
            "triangles": triangles,
            "uv": uv_report,
            "material": material,
        }

    delivery = write_multi_gltf(
        primitives,
        root,
        name="sentinel_rifle_recessed_multimat",
    )
    source_triangles = len(triangulate(asset.mesh).faces)
    acceptance = {
        "recess_variant_valid": recess_state["status"] == "pass",
        "inset_is_below_outer_face": float(recess_state["inset_clearance"]) > 0.010,
        "all_components_assigned_once": sum(
            int(record["component_count"]) for record in group_receipts.values()
        ) == len(asset.components),
        "triangle_conservation": grouped_triangles == source_triangles == int(delivery["triangles"]),
        "four_primitives": int(delivery["primitive_count"]) == 4,
        "four_materials": int(delivery["material_count"]) == 4,
        "gltf_structural_valid": delivery["validation"]["status"] == "pass",
        "shared_world_uv_scale": all(
            record["uv"]["method"] == f"box_projection_world:{world_units_per_tile:.9g}"
            for record in group_receipts.values()
        ),
    }
    manifest: dict[str, object] = {
        "schema": SCHEMA,
        "asset": asset.name,
        "variant": "receiver_true_recess_v0.1",
        "recess_state": recess_state,
        "surface_scale": {
            "world_units_per_tile": world_units_per_tile,
            "texture_size_px": texture_size,
            "nominal_pixels_per_world_unit": texture_size / world_units_per_tile,
        },
        "groups": group_receipts,
        "delivery": delivery,
        "acceptance": acceptance,
        "truth": {
            "preferred_route_claim": False,
            "production_weapon_art_claim": False,
            "notes": [
                "This is a parallel A/B package derived from the validated recessed receiver variant.",
                "The base preferred four-material rifle remains untouched until the same retained Godot views show this variant is actually better.",
                "One true cavity is being evaluated; this is not a claim of general boolean/CSG support.",
            ],
        },
    }
    payload = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8")
    (root / "weapon-recess-multimat.json").write_bytes(payload)
    manifest["manifest_sha256"] = "sha256:" + hashlib.sha256(payload).hexdigest()
    return manifest
