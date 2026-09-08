#!/usr/bin/env python3
"""Godot-ready rifle contact v0.5 with source-grounded articulated fingers."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from native_fabric_material import FabricSpec, write_fabric_material
from native_geometry import Mesh, triangulate
from native_hm08_extremity_gear import _load_identity_body
from native_hm08_finger_grip_pose_v2 import build_hm08_finger_grip_pose_v2
from native_hm08_rifle_contact_pose import _add, _quat_rotate
from native_multi_gltf import MaterialPrimitive, write_multi_gltf
from native_pbr import write_painted_metal
from native_uv import box_project_world, validate_uv
from native_weapon import validate_weapon
from native_weapon_human_scale import human_scale_weapon_evidence, sentinel_rifle_human_scale
from native_weapon_multimat import DEFAULT_WORLD_UNITS_PER_TILE, GROUP_ORDER, _material_specs, semantic_material_groups

SCHEMA = "axm.game-assets.hm08-rifle-contact-package.v0.5"
ASSET_NAME = "sentinel_hm08_rifle_contact_v0_5"


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
    body_m, _uv, identity_state = _load_identity_body()
    posed_body, grip = build_hm08_finger_grip_pose_v2(body_m)
    body_uv = box_project_world(posed_body, world_units_per_tile=0.18)
    body_uv_report = validate_uv(posed_body, body_uv)
    if body_uv_report["status"] != "pass":
        raise ValueError(f"articulated contact body UV invalid: {body_uv_report}")
    body_material = write_fabric_material(
        root / "textures" / "contact_body",
        size=texture_size,
        seed=body_seed,
        spec=FabricSpec(
            base_rgb=(38,43,46), warp_threads=72, weft_threads=68,
            weave_depth=0.035, roughness=0.72, fiber_noise=0.040, thickness_hint_mm=1.2,
        ),
    )

    rifle = sentinel_rifle_human_scale()
    rifle_report = validate_weapon(rifle)
    dimensions = human_scale_weapon_evidence(rifle)
    if rifle_report["status"] != "pass" or dimensions["validation"]["status"] != "pass":
        raise ValueError("human-scale rifle invalid before articulated package")
    groups = semantic_material_groups(rifle)
    specs = _material_specs()
    rotation = tuple(float(value) for value in grip["weapon"]["rotation"])
    translation = tuple(float(value) for value in grip["weapon"]["translation"])

    primitives = [MaterialPrimitive(
        posed_body, body_uv, "Forge_ArticulatedGrip_ContactBody",
        "textures/contact_body/base_color.png", "textures/contact_body/normal.png", "textures/contact_body/orm.png",
        metallic_factor=0.0,
    )]
    weapon_triangles = 0
    group_evidence: dict[str, object] = {}
    for group_index, group in enumerate(GROUP_ORDER):
        local = groups[group]["mesh"]
        assert isinstance(local, Mesh)
        uv = box_project_world(local, world_units_per_tile=DEFAULT_WORLD_UNITS_PER_TILE)
        uv_report = validate_uv(local, uv)
        if uv_report["status"] != "pass":
            raise ValueError(f"{group} articulated rifle UV invalid: {uv_report}")
        world = _transform_mesh(local, rotation, translation, name=f"articulated_contact_rifle_{group}")
        spec = specs[group]
        material = write_painted_metal(
            root / "textures" / "rifle" / group,
            size=texture_size,
            seed=weapon_seed + group_index*1009,
            spec=spec["spec"],
        )
        primitives.append(MaterialPrimitive(
            world, uv, str(spec["name"]),
            f"textures/rifle/{group}/base_color.png",
            f"textures/rifle/{group}/normal.png",
            f"textures/rifle/{group}/orm.png",
            metallic_factor=float(spec["metallic_factor"]),
        ))
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
    contact = grip["contact"]
    acceptance = {
        "corrected_finger_grip_v0_2_used": grip["schema"] == "axm.game-assets.hm08-finger-grip-pose.v0.2" and grip["truth"]["thumb_coordinate_space_corrected"] is True,
        "source_grounded_53_joint_rig": grip["finger_rig"]["total_joint_count"] == 53 and grip["finger_rig"]["truth"]["source_grounded"] is True,
        "finger_skin_valid": grip["finger_skin"]["validation"]["status"] == "pass" and grip["finger_skin"]["max_influences"] <= 4,
        "finger_surface_changed": int(grip["finger_changed_vertices"]) > 200,
        "nonfinger_surface_preserved": float(grip["nonfinger_max_delta_from_v0_4_m"]) < 1e-8,
        "palm_primary_contact_exact": float(contact["primary_position_error"]) < 1e-8,
        "palm_support_contact_exact": float(contact["support_position_error"]) < 1e-6,
        "human_scale_rifle_preserved": 0.92 <= float(dimensions["overall_length_m"]) <= 1.04,
        "rifle_not_runtime_scaled": grip["weapon"]["scale"] == [1.0,1.0,1.0],
        "five_semantic_primitives": delivery["primitive_count"] == 5,
        "five_semantic_materials": delivery["material_count"] == 5,
        "weapon_triangle_conservation": weapon_triangles == expected_weapon_triangles,
        "gltf_structural_valid": delivery["validation"]["status"] == "pass",
    }
    manifest: dict[str, object] = {
        "schema": SCHEMA,
        "asset": ASSET_NAME,
        "candidate_role": "articulated_finger_shared_rig_rifle_contact_visual_proof",
        "changed_variable_from_v0_4": "source_grounded_finger_articulation_only",
        "identity_target_state": identity_state,
        "grip": grip,
        "body_diagnostic_material": body_material,
        "body_uv": body_uv_report,
        "rifle": {
            "source_validation": rifle_report,
            "dimensional_evidence": dimensions,
            "semantic_groups": group_evidence,
            "world_translation": list(translation),
            "world_rotation": list(rotation),
            "scale": grip["weapon"]["scale"],
            "triangles": expected_weapon_triangles,
        },
        "delivery": delivery,
        "acceptance": acceptance,
        "truth": {
            "v0_4_visual_result_preserved": True,
            "arm_pose_changed": False,
            "weapon_changed": False,
            "production_grip_claim": False,
            "trigger_finger_claim": False,
            "finger_collision_solver_claim": False,
            "automatic_visual_promotion": False,
            "notes": [
                "v0.5 is the first Godot delivery candidate with source-grounded finger pivots and skin weights. The v0.4 arm pose, palm sockets and human-scale rifle are held fixed.",
                "The first grip uses deterministic curl/radius objectives and bounded thumb opposition. It does not yet solve interpenetration or isolate a trigger finger.",
                "Hands-close Godot evidence remains the promotion gate for visible grip readability."
            ],
        },
    }
    payload = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8")
    (root / "rifle-contact-package-v5.json").write_bytes(payload)
    manifest["manifest_sha256"] = _sha(payload)
    if not all(acceptance.values()):
        raise ValueError(f"articulated contact package failed: {acceptance}")
    return manifest


if __name__ == "__main__":
    import argparse
    p=argparse.ArgumentParser();p.add_argument("output",nargs="?",default="build/hm08-rifle-contact-v5");p.add_argument("--texture-size",type=int,default=128);a=p.parse_args()
    r=build_hm08_rifle_contact_package_v5(a.output,texture_size=a.texture_size)
    print(json.dumps({"acceptance":r["acceptance"],"grip":r["grip"],"delivery":r["delivery"]},indent=2))
