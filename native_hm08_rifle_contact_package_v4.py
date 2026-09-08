#!/usr/bin/env python3
"""Godot-ready v0.4 rifle contact package: v0.3 pose + segment arm skin."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from native_fabric_material import FabricSpec, write_fabric_material
from native_geometry import Mesh, triangulate
from native_hm08_extremity_gear import _load_identity_body
from native_hm08_rifle_contact_pose import _add, _quat_rotate
from native_hm08_rifle_contact_pose_v4 import build_segment_skin_rifle_contact_pose
from native_multi_gltf import MaterialPrimitive, write_multi_gltf
from native_pbr import write_painted_metal
from native_uv import box_project_world, validate_uv
from native_weapon import validate_weapon
from native_weapon_human_scale import human_scale_weapon_evidence, sentinel_rifle_human_scale
from native_weapon_multimat import DEFAULT_WORLD_UNITS_PER_TILE, GROUP_ORDER, _material_specs, semantic_material_groups

SCHEMA="axm.game-assets.hm08-rifle-contact-package.v0.4"
ASSET_NAME="sentinel_hm08_rifle_contact_v0_4"


def _sha(data:bytes)->str:
    return "sha256:"+hashlib.sha256(data).hexdigest()


def _transform_mesh(mesh:Mesh,rotation,translation,*,name:str)->Mesh:
    return Mesh(name,[_add(translation,_quat_rotate(rotation,p)) for p in mesh.vertices],list(mesh.faces))


def build_hm08_rifle_contact_package_v4(output:str|Path,*,texture_size:int=128,body_seed:int=97021,weapon_seed:int=8801)->dict[str,object]:
    root=Path(output);root.mkdir(parents=True,exist_ok=True)
    body_m,_uv,identity_state=_load_identity_body()
    posed_body,pose=build_segment_skin_rifle_contact_pose(body_m)
    body_uv=box_project_world(posed_body,world_units_per_tile=0.18)
    body_uv_report=validate_uv(posed_body,body_uv)
    if body_uv_report["status"]!="pass":raise ValueError(body_uv_report)
    body_material=write_fabric_material(
        root/"textures"/"contact_body",size=texture_size,seed=body_seed,
        spec=FabricSpec(base_rgb=(38,43,46),warp_threads=72,weft_threads=68,weave_depth=0.035,roughness=0.72,fiber_noise=0.040,thickness_hint_mm=1.2),
    )
    rifle=sentinel_rifle_human_scale()
    rifle_report=validate_weapon(rifle);dims=human_scale_weapon_evidence(rifle)
    if rifle_report["status"]!="pass" or dims["validation"]["status"]!="pass":raise ValueError("human-scale rifle invalid")
    groups=semantic_material_groups(rifle);specs=_material_specs()
    rotation=tuple(float(v) for v in pose["weapon"]["rotation"])
    translation=tuple(float(v) for v in pose["weapon"]["translation"])
    primitives=[MaterialPrimitive(posed_body,body_uv,"Forge_SegmentSkin_ContactBody_Proposal","textures/contact_body/base_color.png","textures/contact_body/normal.png","textures/contact_body/orm.png",metallic_factor=0.0)]
    weapon_triangles=0;group_evidence={}
    for group_index,group in enumerate(GROUP_ORDER):
        local=groups[group]["mesh"];assert isinstance(local,Mesh)
        uv=box_project_world(local,world_units_per_tile=DEFAULT_WORLD_UNITS_PER_TILE)
        uv_report=validate_uv(local,uv)
        if uv_report["status"]!="pass":raise ValueError(uv_report)
        world=_transform_mesh(local,rotation,translation,name=f"segment_skin_contact_rifle_{group}")
        spec=specs[group]
        material=write_painted_metal(root/"textures"/"rifle"/group,size=texture_size,seed=weapon_seed+group_index*1009,spec=spec["spec"])
        primitives.append(MaterialPrimitive(world,uv,str(spec["name"]),f"textures/rifle/{group}/base_color.png",f"textures/rifle/{group}/normal.png",f"textures/rifle/{group}/orm.png",metallic_factor=float(spec["metallic_factor"])))
        tris=len(triangulate(local).faces);weapon_triangles+=tris
        group_evidence[group]={"components":groups[group]["components"],"triangles":tris,"uv":uv_report,"material":material}
    delivery=write_multi_gltf(primitives,root,name=ASSET_NAME)
    expected=len(triangulate(rifle.mesh).faces)
    acceptance={
        "segment_skin_v0_2_used":pose["truth"]["segment_skin_v0_2_used"] is True and pose["shared_rig"]["skin_evidence"]["schema"]=="axm.game-assets.hm08-humanoid-skin.v0.2",
        "joint_pose_preserved":pose["truth"]["joint_pose_preserved_from_v0_3"] is True,
        "human_scale_rifle_preserved":pose["truth"]["human_scale_rifle_preserved"] is True and 0.92<=float(dims["overall_length_m"])<=1.04,
        "rifle_not_runtime_scaled":pose["weapon"]["scale"]==[1.0,1.0,1.0],
        "primary_contact_exact":float(pose["contact"]["primary_position_error"])<1e-8,
        "support_contact_exact":float(pose["contact"]["support_position_error"])<1e-6,
        "right_hand_surface_near_socket":float(pose["hand_visual_contact"]["right"]["centroid_to_socket_error_m"])<0.060,
        "left_hand_surface_near_socket":float(pose["hand_visual_contact"]["left"]["centroid_to_socket_error_m"])<0.060,
        "head_unchanged":float(pose["head_max_displacement_m"])<1e-9,
        "lower_body_unchanged":float(pose["lower_body_max_displacement_m"])<1e-9,
        "five_semantic_primitives":delivery["primitive_count"]==5,
        "weapon_triangle_conservation":weapon_triangles==expected,
        "gltf_structural_valid":delivery["validation"]["status"]=="pass",
    }
    manifest={
        "schema":SCHEMA,"asset":ASSET_NAME,"candidate_role":"segment_skin_shared_rig_rifle_contact_visual_proof",
        "changed_variable_from_v0_3":"arm_skin_weights_only","identity_target_state":identity_state,"pose":pose,
        "body_diagnostic_material":body_material,"body_uv":body_uv_report,
        "rifle":{"source_validation":rifle_report,"dimensional_evidence":dims,"semantic_groups":group_evidence,"world_translation":list(translation),"world_rotation":list(rotation),"scale":pose["weapon"]["scale"],"triangles":expected},
        "delivery":delivery,"acceptance":acceptance,
        "truth":{"v0_3_visual_result_preserved":True,"production_skinning_claim":False,"finger_chain_claim":False,"automatic_visual_promotion":False,"notes":[
            "v0.4 preserves the human-scale rifle and exact v0.3 contact pose while replacing only arm weights with segment skin v0.2.",
            "Any Godot change from v0.3 is a skinning result. Open/relaxed hand geometry remains intentionally visible until finger chains are built."
        ]},
    }
    payload=(json.dumps(manifest,indent=2,sort_keys=True)+"\n").encode();(root/"rifle-contact-package-v4.json").write_bytes(payload);manifest["manifest_sha256"]=_sha(payload)
    if not all(acceptance.values()):raise ValueError(f"v0.4 contact package failed: {acceptance}")
    return manifest


if __name__=="__main__":
    import argparse
    p=argparse.ArgumentParser();p.add_argument("output",nargs="?",default="build/hm08-rifle-contact-v4");p.add_argument("--texture-size",type=int,default=128);a=p.parse_args()
    r=build_hm08_rifle_contact_package_v4(a.output,texture_size=a.texture_size);print(json.dumps({"acceptance":r["acceptance"],"pose":r["pose"],"delivery":r["delivery"]},indent=2))
