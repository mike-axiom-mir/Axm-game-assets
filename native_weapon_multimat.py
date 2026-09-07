#!/usr/bin/env python3
"""AXM Sentinel rifle semantic multi-material package v0.2.

This package preserves named material groups and a shared physical UV scale.
It remains independent from the legacy one-material rifle delivery so engine
A/B evidence can decide which route graduates.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from native_geometry import Mesh, combine, triangulate
from native_multi_gltf import MaterialPrimitive, write_multi_gltf
from native_pbr import PaintedMetalSpec, write_painted_metal
from native_uv import box_project_world, validate_uv
from native_weapon import WeaponAsset, sentinel_rifle, validate_weapon

SCHEMA = "axm.game-assets.weapon-multimat.v0.2"
GROUP_ORDER = ("coated", "polymer", "steel", "accessory")
DEFAULT_WORLD_UNITS_PER_TILE = 0.18

POLYMER_EXACT = {
    "stock_core",
    "stock_spine",
    "stock_lower_brace",
    "cheek_rest",
    "stock_pad",
    "rear_sling_mount",
    "primary_grip",
    "primary_grip_cap",
    "foregrip",
    "foregrip_cap",
    "magazine",
    "magazine_base",
}
STEEL_EXACT = {"barrel", "barrel_shroud", "trigger"}
ACCESSORY_EXACT = {
    "upper_rail_spine",
    "rear_sight",
    "front_sight",
    "optic_base",
    "optic_body",
    "optic_front_ring",
    "optic_rear_ring",
    "side_module",
    "side_module_cap",
    "ejection_port_plate",
    "handguard_left_rail",
    "handguard_right_rail",
    "handguard_bottom_rail",
}


def component_group(name: str) -> str:
    if name in POLYMER_EXACT:
        return "polymer"
    if (
        name in STEEL_EXACT
        or name.startswith("barrel_collar_")
        or name.startswith("muzzle_")
        or name.startswith("fastener_")
    ):
        return "steel"
    if name in ACCESSORY_EXACT or name.startswith("upper_rail_tooth_"):
        return "accessory"
    return "coated"


def semantic_material_groups(asset: WeaponAsset) -> dict[str, dict[str, object]]:
    grouped_components: dict[str, list[Mesh]] = {group: [] for group in GROUP_ORDER}
    grouped_names: dict[str, list[str]] = {group: [] for group in GROUP_ORDER}
    for component_name, mesh in asset.components.items():
        group = component_group(component_name)
        grouped_components[group].append(mesh)
        grouped_names[group].append(component_name)

    result: dict[str, dict[str, object]] = {}
    assigned = sum(len(items) for items in grouped_names.values())
    if assigned != len(asset.components):
        raise ValueError("semantic material grouping lost weapon components")
    for group in GROUP_ORDER:
        meshes = grouped_components[group]
        if not meshes:
            raise ValueError(f"semantic material group {group} is empty")
        combined = combine(meshes, name=f"{asset.name}_{group}")
        result[group] = {
            "mesh": combined,
            "components": sorted(grouped_names[group]),
            "triangles": len(triangulate(combined).faces),
        }
    return result


def _material_specs() -> dict[str, dict[str, object]]:
    return {
        "coated": {
            "name": "AXM_Weapon_CoatedReceiver",
            "spec": PaintedMetalSpec(
                paint_rgb=(30, 38, 43),
                metal_rgb=(76, 82, 86),
                paint_roughness=0.62,
                metal_roughness=0.39,
                wear=0.15,
                scratches=22,
                grain_scale=34.0,
            ),
            "metallic_factor": 1.0,
        },
        "polymer": {
            "name": "AXM_Weapon_DarkPolymer",
            "spec": PaintedMetalSpec(
                paint_rgb=(14, 17, 19),
                metal_rgb=(24, 27, 29),
                paint_roughness=0.82,
                metal_roughness=0.78,
                wear=0.025,
                scratches=10,
                grain_scale=48.0,
            ),
            "metallic_factor": 0.0,
        },
        "steel": {
            "name": "AXM_Weapon_ExposedSteel",
            "spec": PaintedMetalSpec(
                paint_rgb=(66, 70, 72),
                metal_rgb=(112, 118, 121),
                paint_roughness=0.43,
                metal_roughness=0.31,
                wear=0.58,
                scratches=30,
                grain_scale=42.0,
            ),
            "metallic_factor": 1.0,
        },
        "accessory": {
            "name": "AXM_Weapon_MatteAccessory",
            "spec": PaintedMetalSpec(
                paint_rgb=(20, 24, 27),
                metal_rgb=(55, 59, 62),
                paint_roughness=0.71,
                metal_roughness=0.48,
                wear=0.09,
                scratches=16,
                grain_scale=38.0,
            ),
            "metallic_factor": 0.65,
        },
    }


def build_weapon_multimat_package(
    output: str | Path,
    *,
    texture_size: int = 64,
    seed: int = 8801,
    world_units_per_tile: float = DEFAULT_WORLD_UNITS_PER_TILE,
) -> dict[str, object]:
    root = Path(output)
    root.mkdir(parents=True, exist_ok=True)
    asset = sentinel_rifle()
    weapon_report = validate_weapon(asset)
    if weapon_report["status"] != "pass":
        raise ValueError(f"weapon failed before material grouping: {weapon_report}")

    groups = semantic_material_groups(asset)
    specs = _material_specs()
    primitives: list[MaterialPrimitive] = []
    group_receipts: dict[str, object] = {}
    total_group_triangles = 0

    for group_index, group in enumerate(GROUP_ORDER):
        group_mesh = groups[group]["mesh"]
        assert isinstance(group_mesh, Mesh)
        # All material groups share the exact same canonical-space scale and
        # origin. UV phase may cross 0/1 boundaries; glTF repeat sampling is
        # intentional so surface feature size no longer depends on group bounds.
        uv = box_project_world(
            group_mesh,
            world_units_per_tile=world_units_per_tile,
            origin=(0.0, 0.0, 0.0),
        )
        uv_report = validate_uv(group_mesh, uv)
        if uv_report["status"] != "pass":
            raise ValueError(f"{group} UV failed: {uv_report}")
        texture_dir = root / "textures" / group
        spec_record = specs[group]
        material = write_painted_metal(
            texture_dir,
            size=texture_size,
            seed=seed + group_index * 1009,
            spec=spec_record["spec"],
        )
        base_uri = f"textures/{group}/base_color.png"
        normal_uri = f"textures/{group}/normal.png"
        orm_uri = f"textures/{group}/orm.png"
        primitives.append(
            MaterialPrimitive(
                group_mesh,
                uv,
                str(spec_record["name"]),
                base_uri,
                normal_uri,
                orm_uri,
                metallic_factor=float(spec_record["metallic_factor"]),
            )
        )
        triangles = int(groups[group]["triangles"])
        total_group_triangles += triangles
        group_receipts[group] = {
            "material_name": spec_record["name"],
            "metallic_factor": spec_record["metallic_factor"],
            "components": groups[group]["components"],
            "component_count": len(groups[group]["components"]),
            "triangles": triangles,
            "surface_scale": {
                "projection": "world_box_repeat",
                "world_units_per_tile": world_units_per_tile,
                "origin": [0.0, 0.0, 0.0],
                "texture_size_px": texture_size,
                "nominal_pixels_per_world_unit": texture_size / world_units_per_tile,
            },
            "uv": uv_report,
            "material": material,
        }

    delivery = write_multi_gltf(primitives, root, name="sentinel_rifle_multimat")
    source_triangles = len(triangulate(asset.mesh).faces)
    expected_uv_method = f"box_projection_world:{world_units_per_tile:.9g}"
    acceptance = {
        "weapon_state_valid": weapon_report["status"] == "pass",
        "all_components_assigned_once": sum(
            int(record["component_count"]) for record in group_receipts.values()
        ) == len(asset.components),
        "four_nonempty_material_groups": len(group_receipts) == 4
        and all(int(record["component_count"]) > 0 for record in group_receipts.values()),
        "group_triangle_conservation": total_group_triangles == source_triangles,
        "delivery_triangle_conservation": int(delivery["triangles"]) == source_triangles,
        "four_gltf_primitives": int(delivery["primitive_count"]) == 4,
        "four_gltf_materials": int(delivery["material_count"]) == 4,
        "gltf_structural_valid": delivery["validation"]["status"] == "pass",
        "polymer_nonmetal": float(group_receipts["polymer"]["metallic_factor"]) == 0.0,
        "distinct_material_identities": len(set(delivery["material_names"])) == 4,
        "shared_physical_uv_scale": all(
            record["uv"]["method"] == expected_uv_method for record in group_receipts.values()
        ),
    }
    manifest: dict[str, object] = {
        "schema": SCHEMA,
        "asset": asset.name,
        "source_weapon": weapon_report,
        "surface_scale": {
            "projection": "world_box_repeat",
            "world_units_per_tile": world_units_per_tile,
            "texture_size_px": texture_size,
            "nominal_pixels_per_world_unit": texture_size / world_units_per_tile,
            "authority": "deterministic_authoring_state",
        },
        "groups": group_receipts,
        "delivery": delivery,
        "acceptance": acceptance,
        "truth": {
            "production_material_claim": False,
            "measured_material_claim": False,
            "atlas_pack_claim": False,
            "notes": [
                "Semantic material groups are derived from named canonical weapon components before export.",
                "All groups share one world-space repeat scale, so material feature size no longer changes with material-group bounds.",
                "World-box repeat projection preserves physical scale but does not claim optimized unwrap charts, seam hiding, unique baking space or final texel-density art direction.",
                "The polymer primitive explicitly uses metallicFactor 0 instead of relying on a shared weapon material.",
                "Godot close-inspection views remain the visual gate for visible seams, repetition and surface swimming.",
            ],
        },
    }
    payload = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8")
    (root / "weapon-multimat.json").write_bytes(payload)
    manifest["manifest_sha256"] = "sha256:" + hashlib.sha256(payload).hexdigest()
    return manifest
