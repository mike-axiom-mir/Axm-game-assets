#!/usr/bin/env python3
"""Godot-ready shared-rig contact package with human-scale rifle v0.3."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from native_fabric_material import FabricSpec, write_fabric_material
from native_geometry import Mesh, triangulate
from native_hm08_extremity_gear import _load_identity_body
from native_hm08_rifle_contact_pose import _add, _quat_rotate
from native_hm08_rifle_contact_pose_v3 import build_human_scale_rifle_contact_pose
from native_multi_gltf import MaterialPrimitive, write_multi_gltf
from native_pbr import write_painted_metal
from native_uv import box_project_world, validate_uv
from native_weapon import validate_weapon
from native_weapon_human_scale import human_scale_weapon_evidence, sentinel_rifle_human_scale
from native_weapon_multimat import DEFAULT_WORLD_UNITS_PER_TILE, GROUP_ORDER, _material_specs, semantic_material_groups

SCHEMA = "axm.game-assets.hm08-rifle-contact-package.v0.3"
ASSET_NAME = "sentinel_hm08_rifle_contact_v0_3"


def _sha(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _transform_mesh(mesh: Mesh, rotation, translation, *, name: str) -> Mesh:
    return Mesh(name, [_add(translation, _quat_rotate(rotation, point)) for point in mesh.vertices], list(mesh.faces))


def build_hm08_rifle_contact_package_v3(
    output: str | Path,
    *,
    texture_size: int = 128,
    body_seed: int = 97021,
    weapon_seed: int = 8801,
) -> dict[str, object]:
    root = Path(output)
    root.mkdir(parents=True, exist_ok=True)
    body_m, _uv, identity_state = _load_identity_body()
    posed_body, pose = build_human_scale_rifle_contact_pose(body_m)
    body_uv = box_project_world(posed_body, world_units_per_tile=0.18)
    body_uv_report = validate_uv(posed_body, body_uv)
    if body_uv_report["status"] != "pass":
        raise ValueError(f"v0.3 contact body UV invalid: {body_uv_report}")
    body_material = write_fabric_material(
        root / "textures" / "contact_body",
        size=texture_size,
        seed=body_seed,
        spec=FabricSpec(base_rgb=(38,43,46), warp_threads=72, weft_threads=68, weave_depth=0.035, roughness=0.72, fiber_noise=0.040, thickness_hint_mm=1.2),
    )

    rifle = sentinel_rifle_human_scale()
    rifle_report = validate_weapon(rifle)
    rifle_dimensions = human_scale_weapon_evidence(rifle)
    if rifle_report["status"] != "pass" or rifle_dimensions["validation"]["status"] != "pass":
        raise ValueError("human-scale rifle failed package validation")
    groups = semantic_material_groups(rifle)
    specs = _material_specs()
    rotation = tuple(float(v) for v in pose["weapon"]["rotation"])
    translation = tuple(float(v) for v in pose["weapon"]["translation"])

    primitives = [MaterialPrimitive(
        posed_body, body_uv, "Forge_SharedRig_ContactBody_Proposal",
        "textures/contact_body/base_color.png", "textures/contact_body/normal.png", "textures/contact_body/orm.png",
        metallic_factor=0.0,
    )]
    rifle_groups: dict[str, object] = {}
    weapon_triangles = 0
    for group_index, group in enumerate(GROUP_ORDER):
        local_mesh = groups[group]["mesh"]
        assert isinstance(local_mesh, Mesh)
        local_uv = box_project_world(local_mesh, world_units_per_tile=DEFAULT_WORLD_UNITS_PER_TILE)
        uv_report = validate_uv(local_mesh, local_uv)
        if uv_report["status"] != "pass":
            raise ValueError(f"{group} human-scale rifle UV invalid: {uv_report}")
        world_mesh = _transform_mesh(local_mesh, rotation, translation, name=f"human_scale_contact_rifle_{group}")
        spec_record = specs[group]
        material = write_painted_metal(
            root / "textures" / "rifle" / group,
            size=texture_size,
            seed=weapon_seed + group_index*1009,
            spec=spec_record["spec"],
        )
        primitives.append(MaterialPrimitive(
            world_mesh, local_uv, str(spec_record["name"]),
            f"textures/rifle/{group}/base_color.png",
            f"textures/rifle/{group}/normal.png",
            f"textures/rifle/{group}/orm.png",
            metallic_factor=float(spec_record["metallic_factor"]),
        ))
        triangles = len(triangulate(local_mesh).faces)
        weapon_triangles += triangles
        rifle_groups[group] = {"components":groups[group]["components"],"triangles":triangles,"uv":uv_report,"material":material}

    delivery = write_multi_gltf(primitives, root, name=ASSET_NAME)
    expected_weapon_triangles = len(triangulate(rifle.mesh).faces)
    contact = pose["contact"]
    hand_visual = pose["hand_visual_contact"]
    acceptance = {
        "shared_full_body_rig_used": pose["truth"]["uses_shared_full_body_rig"] is True and pose["shared_rig"]["joint_count"] == 23,
        "human_scale_rifle_used": pose["truth"]["legacy_oversized_rifle_used"] is False and rifle_dimensions["schema"] == "axm.game-assets.sentinel-rifle-human-scale.v0.5",
        "human_scale_length": 0.92 <= float(rifle_dimensions["overall_length_m"]) <= 1.04,
        "rifle_not_runtime_scaled": pose["weapon"]["scale"] == [1.0,1.0,1.0],
        "primary_contact_exact": float(contact["primary_position_error"]) < 1e-8,
        "support_contact_exact": float(contact["support_position_error"]) < 1e-6,
        "right_hand_surface_near_socket": float(hand_visual["right"]["centroid_to_socket_error_m"]) < 0.060,
        "left_hand_surface_near_socket": float(hand_visual["left"]["centroid_to_socket_error_m"]) < 0.060,
        "head_unchanged": float(pose["head_max_displacement_m"]) < 1e-9,
        "lower_body_unchanged": float(pose["lower_body_max_displacement_m"]) < 1e-9,
        "five_semantic_primitives": delivery["primitive_count"] == 5,
        "weapon_triangle_conservation": weapon_triangles == expected_weapon_triangles,
        "gltf_structural_valid": delivery["validation"]["status"] == "pass",
    }
    manifest: dict[str, object] = {
        "schema": SCHEMA,
        "asset": ASSET_NAME,
        "candidate_role": "human_scale_shared_rig_rifle_contact_visual_proof",
        "changed_variable_from_v0_2": "weapon_source_dimensions_only",
        "identity_target_state": identity_state,
        "pose": pose,
        "body_diagnostic_material": body_material,
        "body_uv": body_uv_report,
        "rifle": {
            "source_validation": rifle_report,
            "dimensional_evidence": rifle_dimensions,
            "semantic_groups": rifle_groups,
            "world_translation": list(translation),
            "world_rotation": list(rotation),
            "scale": pose["weapon"]["scale"],
            "triangles": expected_weapon_triangles,
        },
        "delivery": delivery,
        "acceptance": acceptance,
        "truth": {
            "legacy_v0_2_visual_result_preserved": True,
            "production_rig_claim": False,
            "production_skinning_claim": False,
            "rigid_armor_contact_claim": False,
            "automatic_visual_promotion": False,
            "notes": [
                "The v0.2 Godot artifact is retained as the rejected oversized-rifle control.",
                "v0.3 preserves shared rig, palm sockets, contact logic and pose intent while changing only the authored weapon dimensions.",
                "Godot must still decide whether the reduced weapon restores readable character proportions; deformation remains a separate repair target."
            ],
        },
    }
    payload=(json.dumps(manifest,indent=2,sort_keys=True)+"\n").encode("utf-8")
    (root/"rifle-contact-package-v3.json").write_bytes(payload)
    manifest["manifest_sha256"]=_sha(payload)
    if not all(acceptance.values()):
        raise ValueError(f"human-scale contact package failed: {acceptance}")
    return manifest


if __name__ == "__main__":
    import argparse
    parser=argparse.ArgumentParser()
    parser.add_argument("output",nargs="?",default="build/hm08-rifle-contact-v3")
    parser.add_argument("--texture-size",type=int,default=128)
    args=parser.parse_args()
    result=build_hm08_rifle_contact_package_v3(args.output,texture_size=args.texture_size)
    print(json.dumps({"acceptance":result["acceptance"],"pose":result["pose"],"rifle":result["rifle"]["dimensional_evidence"],"delivery":result["delivery"]},indent=2))
