#!/usr/bin/env python3
"""Godot-ready v0.8 DQS deformation package for the proven v0.7 grip."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from native_fabric_material import FabricSpec, write_fabric_material
from native_geometry import Mesh, triangulate
from native_hm08_extremity_gear import _load_identity_body
from native_hm08_rifle_contact_pose import _add, _quat_rotate
from native_hm08_rifle_grip_dqs import build_grip_dqs_pose
from native_hm08_rifle_grip_surface_pose import build_grip_surface_finger_pose
from native_multi_gltf import MaterialPrimitive, write_multi_gltf
from native_pbr import write_painted_metal
from native_uv import box_project_world, validate_uv
from native_weapon import validate_weapon
from native_weapon_human_scale import human_scale_weapon_evidence, sentinel_rifle_human_scale
from native_weapon_multimat import DEFAULT_WORLD_UNITS_PER_TILE, GROUP_ORDER, _material_specs, semantic_material_groups

SCHEMA="axm.game-assets.hm08-rifle-grip-dqs-package.v0.8"
ASSET_NAME="sentinel_hm08_rifle_grip_dqs_v0_8"


def _sha(data:bytes)->str:
    return "sha256:"+hashlib.sha256(data).hexdigest()


def _transform_mesh(mesh:Mesh,rotation,translation,*,name:str)->Mesh:
    return Mesh(name,[_add(translation,_quat_rotate(rotation,p)) for p in mesh.vertices],list(mesh.faces))


def build_hm08_rifle_grip_dqs_package(output:str|Path,*,texture_size:int=128,body_seed:int=97021,weapon_seed:int=8801)->dict[str,object]:
    root=Path(output);root.mkdir(parents=True,exist_ok=True)
    body_m,_uv,identity_state=_load_identity_body()
    dqs_body,dqs=build_grip_dqs_pose(body_m)
    _lbs_body,contact_pose=build_grip_surface_finger_pose(body_m)
    body_uv=box_project_world(dqs_body,world_units_per_tile=0.18)
    body_uv_report=validate_uv(dqs_body,body_uv)
    if body_uv_report["status"]!="pass":raise ValueError(body_uv_report)
    body_material=write_fabric_material(
        root/"textures"/"contact_body",size=texture_size,seed=body_seed,
        spec=FabricSpec(base_rgb=(38,43,46),warp_threads=72,weft_threads=68,weave_depth=0.035,roughness=0.72,fiber_noise=0.040,thickness_hint_mm=1.2),
    )
    rifle=sentinel_rifle_human_scale();rifle_report=validate_weapon(rifle);dims=human_scale_weapon_evidence(rifle)
    if rifle_report["status"]!="pass" or dims["validation"]["status"]!="pass":raise ValueError("human-scale rifle invalid")
    groups=semantic_material_groups(rifle);specs=_material_specs()
    rotation=tuple(float(v) for v in contact_pose["weapon"]["rotation"])
    translation=tuple(float(v) for v in contact_pose["weapon"]["translation"])
    primitives=[MaterialPrimitive(dqs_body,body_uv,"Forge_GripSurface_FingerDQS_Body","textures/contact_body/base_color.png","textures/contact_body/normal.png","textures/contact_body/orm.png",metallic_factor=0.0)]
    weapon_triangles=0;group_evidence={}
    for group_index,group in enumerate(GROUP_ORDER):
        local=groups[group]["mesh"];assert isinstance(local,Mesh)
        uv=box_project_world(local,world_units_per_tile=DEFAULT_WORLD_UNITS_PER_TILE);uv_report=validate_uv(local,uv)
        if uv_report["status"]!="pass":raise ValueError(uv_report)
        world=_transform_mesh(local,rotation,translation,name=f"dqs_grip_rifle_{group}")
        spec=specs[group]
        material=write_painted_metal(root/"textures"/"rifle"/group,size=texture_size,seed=weapon_seed+group_index*1009,spec=spec["spec"])
        primitives.append(MaterialPrimitive(world,uv,str(spec["name"]),f"textures/rifle/{group}/base_color.png",f"textures/rifle/{group}/normal.png",f"textures/rifle/{group}/orm.png",metallic_factor=float(spec["metallic_factor"])))
        tris=len(triangulate(local).faces);weapon_triangles+=tris
        group_evidence[group]={"components":groups[group]["components"],"triangles":tris,"uv":uv_report,"material":material}
    delivery=write_multi_gltf(primitives,root,name=ASSET_NAME);expected=len(triangulate(rifle.mesh).faces)
    radial=dqs["radial_preservation"];penetration=dqs["grip_aabb_surface_penetration"]
    acceptance={
        "v0_7_pose_reconstructed_exactly":float(dqs["pose_reconstruction_max_error_m"])<1e-9,
        "nonfinger_surface_preserved":float(dqs["nonfinger_max_delta_from_v0_7_lbs_m"])<1e-10,
        "dqs_improves_radial_volume_error":float(radial["dqs_mean_abs_error_m"])<float(radial["lbs_mean_abs_error_m"]),
        "dqs_improvement_material":float(radial["relative_error"])<0.90,
        "dqs_does_not_materially_worsen_grip_intersection":float(penetration["dqs_max_m"])<=float(penetration["lbs_max_m"])+0.003,
        "same_human_scale_rifle":0.92<=float(dims["overall_length_m"])<=1.04,
        "rifle_not_runtime_scaled":contact_pose["weapon"]["scale"]==[1.0,1.0,1.0],
        "source_grounded_53_joint_rig":dqs["finger_rig"]["total_joint_count"]==53,
        "five_semantic_primitives":delivery["primitive_count"]==5,
        "weapon_triangle_conservation":weapon_triangles==expected,
        "gltf_structural_valid":delivery["validation"]["status"]=="pass",
    }
    manifest={
        "schema":SCHEMA,"asset":ASSET_NAME,"candidate_role":"same_grip_pose_finger_local_dqs_visual_proof",
        "control":"Run3 v0.7 LBS grip-surface/finger-wrap candidate",
        "changed_variable_from_v0_7":"finger_influenced_vertex_deformation_algorithm_lbs_to_dqs",
        "identity_target_state":identity_state,"contact_pose":contact_pose,"dqs":dqs,
        "body_diagnostic_material":body_material,"body_uv":body_uv_report,
        "rifle":{"source_validation":rifle_report,"dimensional_evidence":dims,"semantic_groups":group_evidence,"world_translation":list(translation),"world_rotation":list(rotation),"scale":contact_pose["weapon"]["scale"],"triangles":expected},
        "delivery":delivery,"acceptance":acceptance,
        "truth":{"v0_7_lbs_control_preserved":True,"production_deformation_claim":False,"production_grip_claim":False,"automatic_visual_promotion":False,"notes":[
            "The joint pose, skin weights, palm-surface contact and rifle are identical to v0.7. Only vertices influenced by appended finger joints switch from linear-blend to dual-quaternion deformation.",
            "Native radial-volume retention improves enough to justify a close-view engine A/B, not to claim that the hand already looks production quality.",
            "Shoulder/elbow/wrist deformation, knuckle corrective shapes if still needed, and armor motion clearance remain later Run 3 gates."
        ]},
    }
    payload=(json.dumps(manifest,indent=2,sort_keys=True)+"\n").encode();(root/"rifle-grip-dqs-package.json").write_bytes(payload);manifest["manifest_sha256"]=_sha(payload)
    if not all(acceptance.values()):raise ValueError(f"v0.8 DQS package failed: {acceptance}")
    return manifest


if __name__=="__main__":
    import argparse
    p=argparse.ArgumentParser();p.add_argument("output",nargs="?",default="build/hm08-rifle-grip-dqs");p.add_argument("--texture-size",type=int,default=128);a=p.parse_args()
    r=build_hm08_rifle_grip_dqs_package(a.output,texture_size=a.texture_size);print(json.dumps({"acceptance":r["acceptance"],"dqs":r["dqs"],"delivery":r["delivery"]},indent=2))
