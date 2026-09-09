#!/usr/bin/env python3
"""Godot-ready v0.5 rifle contact package with source-grounded finger grip.

This package intentionally mirrors v0.4's visual evidence contract. Rifle
source geometry, semantic material groups, material seeds, body diagnostic
material, runtime transform and camera class remain fixed. The changed visual
variable is the v0.5 body pose after the merged 53-joint finger skin baseline:
only appended finger-joint rotations are added to the preserved v0.4 arm pose.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from native_fabric_material import FabricSpec, write_fabric_material
from native_geometry import Mesh, triangulate
from native_hm08_rifle_contact_pose import _add, _quat_rotate
from native_hm08_rifle_contact_pose_v5 import build_preferred_finger_grip_rifle_contact_pose
from native_multi_gltf import MaterialPrimitive, write_multi_gltf
from native_pbr import write_painted_metal
from native_uv import box_project_world, validate_uv
from native_weapon import validate_weapon
from native_weapon_human_scale import human_scale_weapon_evidence, sentinel_rifle_human_scale
from native_weapon_multimat import DEFAULT_WORLD_UNITS_PER_TILE, GROUP_ORDER, _material_specs, semantic_material_groups

SCHEMA = "axm.game-assets.hm08-rifle-contact-package.v0.5"
ASSET_NAME = "sentinel_hm08_rifle_contact_v0_5"
CHANGED_VARIABLE = "finger_joint_rotations_only_after_merged_finger_skin_baseline"


def _sha(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _transform_mesh(mesh: Mesh, rotation, translation, *, name: str) -> Mesh:
    return Mesh(name, [_add(translation, _quat_rotate(rotation, point)) for point in mesh.vertices], list(mesh.faces))


def build_hm08_rifle_contact_package_v5(
    output: str | Path,
    *,
    texture_size: int = 128,
    body_seed: int = 97021,
    weapon_seed: int = 8801,
) -> dict[str, object]:
    root = Path(output)
    root.mkdir(parents=True, exist_ok=True)

    posed_body, pose = build_preferred_finger_grip_rifle_contact_pose()
    if not all(pose["acceptance"].values()):
        raise ValueError(f"v0.5 finger grip pose is not green: {pose['acceptance']}")

    body_uv = box_project_world(posed_body, world_units_per_tile=0.18)
    body_uv_report = validate_uv(posed_body, body_uv)
    if body_uv_report["status"] != "pass":
        raise ValueError(f"v0.5 posed body UV invalid: {body_uv_report}")
    body_material = write_fabric_material(
        root / "textures" / "contact_body",
        size=texture_size,
        seed=body_seed,
        spec=FabricSpec(
            base_rgb=(38, 43, 46),
            warp_threads=72,
            weft_threads=68,
            weave_depth=0.035,
            roughness=0.72,
            fiber_noise=0.040,
            thickness_hint_mm=1.2,
        ),
    )

    rifle = sentinel_rifle_human_scale()
    rifle_report = validate_weapon(rifle)
    dimensions = human_scale_weapon_evidence(rifle)
    if rifle_report["status"] != "pass" or dimensions["validation"]["status"] != "pass":
        raise ValueError("human-scale rifle invalid before v0.5 packaging")
    groups = semantic_material_groups(rifle)
    specs = _material_specs()
    rotation = tuple(float(value) for value in pose["weapon"]["rotation"])
    translation = tuple(float(value) for value in pose["weapon"]["translation"])

    primitives = [
        MaterialPrimitive(
            posed_body,
            body_uv,
            "Forge_FingerGrip_ContactBody_Proposal",
            "textures/contact_body/base_color.png",
            "textures/contact_body/normal.png",
            "textures/contact_body/orm.png",
            metallic_factor=0.0,
        )
    ]
    weapon_triangles = 0
    group_evidence: dict[str, object] = {}
    for group_index, group in enumerate(GROUP_ORDER):
        local = groups[group]["mesh"]
        assert isinstance(local, Mesh)
        uv = box_project_world(local, world_units_per_tile=DEFAULT_WORLD_UNITS_PER_TILE)
        uv_report = validate_uv(local, uv)
        if uv_report["status"] != "pass":
            raise ValueError(f"v0.5 rifle {group} UV invalid: {uv_report}")
        world = _transform_mesh(local, rotation, translation, name=f"finger_grip_contact_rifle_{group}")
        material_spec = specs[group]
        material = write_painted_metal(
            root / "textures" / "rifle" / group,
            size=texture_size,
            seed=weapon_seed + group_index * 1009,
            spec=material_spec["spec"],
        )
        primitives.append(
            MaterialPrimitive(
                world,
                uv,
                str(material_spec["name"]),
                f"textures/rifle/{group}/base_color.png",
                f"textures/rifle/{group}/normal.png",
                f"textures/rifle/{group}/orm.png",
                metallic_factor=float(material_spec["metallic_factor"]),
            )
        )
        triangles = len(triangulate(local).faces)
        weapon_triangles += triangles
        group_evidence[group] = {
            "components": groups[group]["components"],
            "triangles": triangles,
            "uv": uv_report,
            "material": material,
        }

    delivery = write_multi_gltf(primitives, root, name=ASSET_NAME)
    expected_weapon_triangles = len(triangulate(rifle.mesh).faces)
    grip = pose["finger_grip"]
    reference = grip["v0_4_arm_and_weapon_reference"]
    finger_skin = pose["shared_rig"]["finger_skin_evidence"]

    acceptance = {
        "source_grounded_53_joint_rig_used": pose["shared_rig"]["joint_count"] == 53 and pose["shared_rig"]["finger_joint_count"] == 30,
        "finger_skin_green": finger_skin["validation"]["status"] == "pass" and finger_skin["minimum_vertices_per_segment"] >= 3,
        "nonfinger_v2_skin_rows_preserved": finger_skin["preserved_nonfinger_rows"] == finger_skin["expected_preserved_nonfinger_rows"],
        "v0_4_arm_joint_rotations_preserved": reference["arm_joint_rotations_preserved"] is True,
        "human_scale_rifle_preserved": 0.92 <= float(dimensions["overall_length_m"]) <= 1.04,
        "rifle_not_runtime_scaled": pose["weapon"]["scale"] == [1.0, 1.0, 1.0],
        "primary_contact_exact": float(reference["primary_position_error_m"]) < 1e-8,
        "support_contact_exact": float(reference["support_position_error_m"]) < 1e-6,
        "every_fingertip_geometrically_closer": float(grip["minimum_fingertip_improvement_m"]) > 1e-6,
        "both_hand_tip_means_closer": all(
            grip["choices"][side]["curled_tip_mean_m"] < grip["choices"][side]["open_tip_mean_m"]
            for side in ("right", "left")
        ),
        "curl_is_finger_local": float(grip["nonfinger_curl_max_displacement_m"]) < 1e-8,
        "head_unchanged_by_curl": float(grip["head_curl_max_displacement_m"]) < 1e-9,
        "lower_body_unchanged_by_curl": float(grip["lower_body_curl_max_displacement_m"]) < 1e-9,
        "finger_curl_bounded": 0.003 < float(grip["finger_curl_max_displacement_m"]) < 0.12,
        "five_semantic_primitives": delivery["primitive_count"] == 5,
        "weapon_triangle_conservation": weapon_triangles == expected_weapon_triangles,
        "gltf_structural_valid": delivery["validation"]["status"] == "pass",
    }

    manifest: dict[str, object] = {
        "schema": SCHEMA,
        "asset": ASSET_NAME,
        "candidate_role": "source_grounded_finger_grip_visual_proof",
        "changed_variable_from_v0_4": CHANGED_VARIABLE,
        "pose": pose,
        "body_diagnostic_material": body_material,
        "body_uv": body_uv_report,
        "rifle": {
            "source_validation": rifle_report,
            "dimensional_evidence": dimensions,
            "semantic_groups": group_evidence,
            "world_translation": list(translation),
            "world_rotation": list(rotation),
            "scale": pose["weapon"]["scale"],
            "triangles": expected_weapon_triangles,
        },
        "delivery": delivery,
        "acceptance": acceptance,
        "truth": {
            "v0_4_rifle_geometry_materials_transform_preserved": True,
            "v0_4_camera_lab_should_be_reused": True,
            "finger_skin_open_baseline_is_merged_state": True,
            "production_grip_claim": False,
            "production_finger_skinning_claim": False,
            "automatic_visual_promotion": False,
            "notes": [
                "The v0.5 package keeps the v0.4 human-scale rifle source, material groups, material seeds and runtime transform unchanged.",
                "The merged 53-joint finger skin intentionally changes the bounded hand/finger neighborhood relative to v0.4's rigid-hand skin before curl. That baseline difference is preserved as explicit evidence rather than mislabeled as pose drift.",
                "Only appended finger-joint rotations change from the merged open-finger baseline to the v0.5 grip candidate.",
                "All ten fingertips move closer to the existing grip sockets geometrically, but only real Godot hand-close evidence may promote the grip visually.",
                "If Godot shows crushed or twisted fingers, the next repair should target grip volume/circumference and knuckle correctives rather than weakening this evidence boundary."
            ],
        },
    }
    payload = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8")
    (root / "rifle-contact-package-v5.json").write_bytes(payload)
    manifest["manifest_sha256"] = _sha(payload)
    if not all(acceptance.values()):
        raise ValueError(f"v0.5 contact package failed: {acceptance}")
    return manifest


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("output", nargs="?", default="build/hm08-rifle-contact-v5")
    parser.add_argument("--texture-size", type=int, default=128)
    args = parser.parse_args()
    result = build_hm08_rifle_contact_package_v5(args.output, texture_size=args.texture_size)
    print(json.dumps({"acceptance": result["acceptance"], "pose": result["pose"], "delivery": result["delivery"]}, indent=2))
