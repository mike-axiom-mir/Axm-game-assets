#!/usr/bin/env python3
"""Kettlejack v0.3: second render-driven visual repair pass.

v0.2 proved the new visual rehearsal loop works. Its retained Godot renders then
exposed the next bounded gaps: mask-like eyes/goggles, a skin-tight body read,
weak facial identity, a fork-like wrench silhouette and conservative animation
poses. This module repairs those exact visible failures while reusing the v0.2
body/rig/material substrate.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Iterable

from native_animation import AnimationClip, AnimationTrack, validate_animation_clip
from native_construction_kit import beam_segment, rounded_box, torus_ring
from native_geometry import Mesh, bounds, combine
from native_hm08_humanoid_rig import build_hm08_humanoid_skeleton, derive_hm08_rig_landmarks
from native_hm08_humanoid_skin_v2 import build_hm08_skin_weights_v2
from native_hm08_undersuit import _load_identity_body, build_hm08_undersuit
from native_kettlejack_character import (
    DESIGN_INTENT,
    METALLIC_FACTORS,
    _pose_quat,
    _rot_track,
    _scale_skeleton,
    _scaled_point,
    _write_materials,
)
from native_kettlejack_character_v2 import (
    EXTRA_MATERIAL_RECIPES,
    _ellipsoid,
    _extra_materials,
    _group_accessories,
    _head_region,
    _visual_accessories,
    stylize_body_v2,
)
from native_skin import validate_skeleton
from native_skinned_multi_gltf import SkinnedMaterialPrimitive, rigid_skin_weights, write_skinned_multi_gltf
from native_uv import box_project_world, validate_uv
from native_geometry import scale, topology_report, translate

SCHEMA = "axm.game-assets.kettlejack-character/v0.3"
ASSET_NAME = "kettlejack_game_character_v0_3"
TARGET_HEIGHT_M = 1.30


def _sha(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _filtered_v2_rows(landmarks: dict[str, tuple[float,float,float]], body: Mesh):
    rows = _visual_accessories(landmarks, body)
    banned = (
        "cartoon-eye", "cartoon-pupil", "forehead-goggle", "goggle-band",
        "wrench-staff", "wrench-grip", "wrench-head", "wrench-open-jaw", "wrench-jaw", "wrench-bell",
    )
    return [row for row in rows if not any(token in row[3] for token in banned)]


def _v3_accessories(landmarks: dict[str, tuple[float,float,float]], body: Mesh):
    rows = list(_filtered_v2_rows(landmarks, body))
    lo, hi = bounds(body)
    headbox = _head_region(body)
    chest = landmarks["chest"]
    pelvis = landmarks["pelvis"]
    head = landmarks["head"]
    left_upper = landmarks["left_upper_arm"]
    right_upper = landmarks["right_upper_arm"]
    left_fore = landmarks["left_forearm"]
    right_fore = landmarks["right_forearm"]
    left_hand = landmarks["left_hand"]
    right_hand = landmarks["right_hand"]
    left_thigh = landmarks["left_thigh"]
    right_thigh = landmarks["right_thigh"]
    left_shin = landmarks["left_shin"]
    right_shin = landmarks["right_shin"]

    # --- Face repair: smaller embedded eyes, eyebrows, nose and a mouth line. ---
    eye_y = headbox["min_y"] + headbox["height"] * .48
    front_z = headbox["max_z"]
    eye_dx = headbox["width"] * .18
    eye_r = max(.022, headbox["width"] * .092)
    for side, sx in (("left",-1.0),("right",1.0)):
        cx = sx * eye_dx
        rows.append((_ellipsoid(
            f"kettlejack-v3-eye-{side}",
            (cx, eye_y, front_z-eye_r*.18),
            (eye_r, eye_r*1.08, eye_r*.62), segments=24, rings=12,
        ), "head", "eye_white", "face-eye"))
        rows.append((_ellipsoid(
            f"kettlejack-v3-pupil-{side}",
            (cx, eye_y-.001, front_z+eye_r*.34),
            (eye_r*.34, eye_r*.40, eye_r*.16), segments=18, rings=9,
        ), "head", "eye_dark", "face-pupil"))
        brow_y = eye_y + eye_r*1.18
        if sx < 0:
            a=(cx-eye_r*.60,brow_y-.002,front_z+.010); b=(cx+eye_r*.58,brow_y+eye_r*.12,front_z+.010)
        else:
            a=(cx-eye_r*.58,brow_y+eye_r*.12,front_z+.010); b=(cx+eye_r*.60,brow_y-.002,front_z+.010)
        rows.append((beam_segment(a,b,width=.009,depth=.006,name=f"kettlejack-v3-brow-{side}"),"head","hair","face-brow"))

    rows.append((_ellipsoid(
        "kettlejack-v3-nose",
        (0.0, eye_y-eye_r*.58, front_z+.012),
        (eye_r*.43, eye_r*.55, eye_r*.48), segments=18, rings=9,
    ), "head", "skin", "face-nose"))
    mouth_y = eye_y-eye_r*1.62
    rows.append((beam_segment(
        (-eye_r*.65,mouth_y,front_z+.012),(eye_r*.65,mouth_y+eye_r*.08,front_z+.012),
        width=.007,depth=.005,name="kettlejack-v3-mouth"
    ),"head","eye_dark","face-mouth"))

    # Goggles live clearly on the forehead now rather than on top of the eyes.
    goggle_y = eye_y + headbox["height"]*.31
    goggle_z = front_z + .012
    goggle_dx = eye_dx*.95
    goggle_r = eye_r*.82
    for side,sx in (("left",-1.0),("right",1.0)):
        rows.append((torus_ring(
            (sx*goggle_dx,goggle_y,goggle_z),radius=goggle_r,tube=max(.006,goggle_r*.20),axis="z",
            major_segments=20,minor_segments=6,name=f"kettlejack-v3-goggle-{side}"
        ),"head","steel","forehead-goggle-rim"))
    rows.append((beam_segment(
        (-goggle_r*.30,goggle_y,goggle_z),(goggle_r*.30,goggle_y,goggle_z),width=.009,depth=.008,
        name="kettlejack-v3-goggle-bridge"
    ),"head","steel","forehead-goggle-bridge"))

    # --- Clothing volume repair: chest vest, sleeves, trouser shells and gloves. ---
    rows.append((rounded_box(
        (-.082,chest[1]-.095,hi[2]+.020),(.135,.310,.050),chamfer=.018,name="kettlejack-v3-vest-left"
    ),"chest","outfit","layered-vest-front"))
    rows.append((rounded_box(
        (.082,chest[1]-.095,hi[2]+.020),(.135,.310,.050),chamfer=.018,name="kettlejack-v3-vest-right"
    ),"chest","outfit","layered-vest-front"))
    rows.append((beam_segment(
        (-.075,chest[1]+.055,hi[2]+.048),(-.110,pelvis[1]+.055,hi[2]+.050),width=.026,depth=.016,
        name="kettlejack-v3-harness-left"
    ),"chest","wood","harness-strap"))
    rows.append((beam_segment(
        (.075,chest[1]+.055,hi[2]+.048),(.110,pelvis[1]+.055,hi[2]+.050),width=.026,depth=.016,
        name="kettlejack-v3-harness-right"
    ),"chest","wood","harness-strap"))

    limb_shells = [
        ("left_upper_arm", left_upper, left_fore, .105, .095, "rolled-sleeve"),
        ("right_upper_arm", right_upper, right_fore, .105, .095, "rolled-sleeve"),
        ("left_thigh", left_thigh, left_shin, .135, .120, "baggy-trouser-thigh"),
        ("right_thigh", right_thigh, right_shin, .135, .120, "baggy-trouser-thigh"),
    ]
    for joint,a,b,w,d,role in limb_shells:
        rows.append((beam_segment(a,b,width=w,depth=d,name=f"kettlejack-v3-{joint}-shell"),joint,"outfit",role))
    for joint,point in (("left_hand",left_hand),("right_hand",right_hand)):
        rows.append((rounded_box(
            (point[0],point[1]-.012,point[2]),(.090,.075,.075),chamfer=.020,name=f"kettlejack-v3-{joint}-glove"
        ),joint,"rubber","fingerless-glove-block"))

    # Small chest patch gives the front a readable asymmetrical repair history.
    rows.append((rounded_box(
        (-.085,chest[1]-.125,hi[2]+.052),(.080,.100,.014),chamfer=.006,name="kettlejack-v3-chest-patch"
    ),"chest","ivory_metal","repaired-chest-patch"))

    # --- Wrench repair: broad adjustable/open-jaw head instead of fork geometry. ---
    wx,_wy,wz = right_hand
    tool_z = wz+.070
    shaft_bottom=.045
    shaft_top=min(hi[1]+.105,1.41)
    rows.append((beam_segment(
        (wx,shaft_bottom,tool_z),(wx,shaft_top,tool_z),width=.052,depth=.045,name="kettlejack-v3-wrench-shaft"
    ),"right_hand","rust_red","wrench-staff-shaft"))
    for idx,y in enumerate((.22,.29,.36)):
        rows.append((torus_ring(
            (wx,y,tool_z),radius=.034,tube=.0055,axis="y",major_segments=14,minor_segments=5,
            name=f"kettlejack-v3-wrench-wrap-{idx}"
        ),"right_hand","scarf","wrench-grip-wrap"))
    head_y=shaft_top+.018
    rows.append((rounded_box(
        (wx,head_y,tool_z),(.245,.082,.060),chamfer=.018,name="kettlejack-v3-wrench-head-base"
    ),"right_hand","steel","wrench-head-base"))
    rows.append((beam_segment(
        (wx-.090,head_y+.018,tool_z),(wx-.125,head_y+.145,tool_z),width=.060,depth=.054,
        name="kettlejack-v3-wrench-fixed-jaw"
    ),"right_hand","rust_red","wrench-fixed-jaw"))
    rows.append((beam_segment(
        (wx+.060,head_y+.020,tool_z),(wx+.105,head_y+.120,tool_z),width=.052,depth=.050,
        name="kettlejack-v3-wrench-moving-jaw"
    ),"right_hand","rust_red","wrench-moving-jaw"))
    rows.append((torus_ring(
        (wx+.010,head_y,tool_z+.034),radius=.026,tube=.008,axis="z",major_segments=16,minor_segments=5,
        name="kettlejack-v3-wrench-thumbwheel"
    ),"right_hand","yellow_metal","wrench-thumbwheel"))
    return rows


def build_kettlejack_clips_v3(name_to_index: dict[str,int]) -> tuple[AnimationClip,...]:
    # Stronger silhouette changes and explicit hand counter-rotation for the staff.
    idle_t=[0.0,.8,1.6]
    idle=AnimationClip("idle",[
        _rot_track(name_to_index["left_upper_arm"],idle_t,[{"z":52},{"z":55},{"z":52}]),
        _rot_track(name_to_index["left_forearm"],idle_t,[{"z":18},{"z":22},{"z":18}]),
        _rot_track(name_to_index["right_upper_arm"],idle_t,[{"z":-54},{"z":-57},{"z":-54}]),
        _rot_track(name_to_index["right_forearm"],idle_t,[{"z":-26},{"z":-22},{"z":-26}]),
        _rot_track(name_to_index["right_hand"],idle_t,[{"z":72},{"z":76},{"z":72}]),
        _rot_track(name_to_index["head"],idle_t,[{"y":-4},{"y":5},{"y":-4}]),
        _rot_track(name_to_index["spine_mid"],idle_t,[{"x":-2,"y":-2},{"x":1,"y":2},{"x":-2,"y":-2}]),
    ])

    run_t=[0.0,.18,.36,.54,.72]
    run=AnimationClip("run",[
        _rot_track(name_to_index["left_thigh"],run_t,[{"x":-42},{"x":0},{"x":42},{"x":0},{"x":-42}]),
        _rot_track(name_to_index["right_thigh"],run_t,[{"x":42},{"x":0},{"x":-42},{"x":0},{"x":42}]),
        _rot_track(name_to_index["left_shin"],run_t,[{"x":58},{"x":20},{"x":-12},{"x":20},{"x":58}]),
        _rot_track(name_to_index["right_shin"],run_t,[{"x":-12},{"x":20},{"x":58},{"x":20},{"x":-12}]),
        _rot_track(name_to_index["left_upper_arm"],run_t,[{"x":32,"z":56},{"z":56},{"x":-32,"z":56},{"z":56},{"x":32,"z":56}]),
        _rot_track(name_to_index["right_upper_arm"],run_t,[{"x":-26,"z":-56},{"z":-56},{"x":26,"z":-56},{"z":-56},{"x":-26,"z":-56}]),
        _rot_track(name_to_index["right_hand"],run_t,[{"z":55},{"z":58},{"z":50},{"z":58},{"z":55}]),
        _rot_track(name_to_index["spine_mid"],run_t,[{"x":-13,"y":-7},{"x":-10},{"x":-13,"y":7},{"x":-10},{"x":-13,"y":-7}]),
        _rot_track(name_to_index["head"],run_t,[{"x":8},{"x":5},{"x":8},{"x":5},{"x":8}]),
    ])

    jump_t=[0.0,.22,.46,.76]
    jump=AnimationClip("jump",[
        _rot_track(name_to_index["left_thigh"],jump_t,[{"x":10},{"x":-48},{"x":24},{"x":8}]),
        _rot_track(name_to_index["right_thigh"],jump_t,[{"x":-8},{"x":-32},{"x":48},{"x":-8}]),
        _rot_track(name_to_index["left_shin"],jump_t,[{"x":10},{"x":72},{"x":34},{"x":8}]),
        _rot_track(name_to_index["right_shin"],jump_t,[{"x":8},{"x":58},{"x":72},{"x":8}]),
        _rot_track(name_to_index["left_upper_arm"],jump_t,[{"z":54},{"z":112},{"z":92},{"z":54}]),
        _rot_track(name_to_index["right_upper_arm"],jump_t,[{"z":-54},{"z":-98},{"z":-82},{"z":-54}]),
        _rot_track(name_to_index["right_hand"],jump_t,[{"z":70},{"z":96},{"z":84},{"z":70}]),
        _rot_track(name_to_index["spine_mid"],jump_t,[{"x":0},{"x":18},{"x":-8},{"x":0}]),
    ])

    attack_t=[0.0,.16,.34,.58,.84]
    attack=AnimationClip("wrench_swing",[
        _rot_track(name_to_index["right_upper_arm"],attack_t,[
            {"y":45,"z":-52},{"y":82,"z":-24},{"y":-72,"z":-12},{"y":-96,"z":-46},{"y":45,"z":-52}
        ]),
        _rot_track(name_to_index["right_forearm"],attack_t,[
            {"y":22,"z":-24},{"y":52,"z":-8},{"y":-40,"z":-42},{"y":-20,"z":-22},{"y":22,"z":-24}
        ]),
        _rot_track(name_to_index["right_hand"],attack_t,[
            {"z":62},{"z":34},{"z":-22},{"z":18},{"z":62}
        ]),
        _rot_track(name_to_index["chest"],attack_t,[{"x":-5,"y":-16},{"x":-8,"y":-34},{"x":8,"y":42},{"x":4,"y":28},{"x":-5,"y":-16}]),
        _rot_track(name_to_index["spine_mid"],attack_t,[{"y":-10},{"y":-24},{"y":30},{"y":18},{"y":-10}]),
        _rot_track(name_to_index["left_upper_arm"],attack_t,[{"z":58},{"z":74},{"z":42},{"z":50},{"z":58}]),
    ])

    victory_t=[0.0,.30,.66,1.02]
    victory=AnimationClip("victory",[
        _rot_track(name_to_index["left_upper_arm"],victory_t,[{"z":54},{"z":88},{"z":76},{"z":54}]),
        _rot_track(name_to_index["left_forearm"],victory_t,[{"z":18},{"z":-72},{"z":-48},{"z":18}]),
        _rot_track(name_to_index["right_upper_arm"],victory_t,[{"z":-54},{"z":-92},{"z":-80},{"z":-54}]),
        _rot_track(name_to_index["right_forearm"],victory_t,[{"z":-24},{"z":76},{"z":54},{"z":-24}]),
        _rot_track(name_to_index["right_hand"],victory_t,[{"z":70},{"z":104},{"z":92},{"z":70}]),
        _rot_track(name_to_index["left_thigh"],victory_t,[{"x":0},{"x":-26},{"x":12},{"x":0}]),
        _rot_track(name_to_index["right_shin"],victory_t,[{"x":0},{"x":62},{"x":34},{"x":0}]),
        _rot_track(name_to_index["head"],victory_t,[{"y":0},{"x":-8,"y":-12},{"x":-4,"y":10},{"y":0}]),
        _rot_track(name_to_index["spine_mid"],victory_t,[{"x":0},{"x":-10,"y":-8},{"x":-6,"y":6},{"x":0}]),
    ])
    return idle,run,jump,attack,victory


def write_kettlejack_v3_package(output: str|Path,*,texture_size:int=64,target_height_m:float=TARGET_HEIGHT_M)->dict[str,Any]:
    root=Path(output)
    root.mkdir(parents=True,exist_ok=True)
    if any(root.iterdir()):
        raise FileExistsError(f"Kettlejack v0.3 output must start empty: {root}")

    source_body,body_uv,target_state=_load_identity_body()
    styled,stylization=stylize_body_v2(source_body)
    if validate_uv(styled,body_uv)["status"]!="pass":
        raise ValueError("stylized body UV invalid")
    skeleton,rig_evidence,name_to_index=build_hm08_humanoid_skeleton(styled)
    landmarks=derive_hm08_rig_landmarks(styled)
    body_weights,skin_evidence=build_hm08_skin_weights_v2(styled,skeleton,landmarks,name_to_index)
    undersuit,undersuit_uv,undersuit_evidence=build_hm08_undersuit(styled,body_uv,offset_m=.0055)
    undersuit_weights,undersuit_skin_evidence=build_hm08_skin_weights_v2(undersuit,skeleton,landmarks,name_to_index)

    lo,hi=bounds(styled)
    source_height=hi[1]-lo[1]
    factor=target_height_m/source_height
    scaled_body=scale(styled,factor,name="kettlejack-v3-body")
    scaled_outfit=scale(undersuit,factor,name="kettlejack-v3-outfit")
    scaled_lo,_=bounds(scaled_body)
    ground_offset=-scaled_lo[1]
    body=translate(scaled_body,(0,ground_offset,0),name="kettlejack-v3-body")
    outfit=translate(scaled_outfit,(0,ground_offset,0),name="kettlejack-v3-outfit")
    scaled_skeleton=_scale_skeleton(skeleton,factor,ground_offset)
    scaled_landmarks={name:_scaled_point(point,factor,ground_offset) for name,point in landmarks.items()}
    grounded_lo,grounded_hi=bounds(body)
    actual_height=grounded_hi[1]-grounded_lo[1]

    materials=_write_materials(root,texture_size)
    _extra_materials(root,texture_size,materials)
    metallic={**METALLIC_FACTORS,**{name:float(recipe["metallic"]) for name,recipe in EXTRA_MATERIAL_RECIPES.items()}}

    primitives=[
        SkinnedMaterialPrimitive(body,body_uv,body_weights,"Kettlejack_v3_Skin",materials["skin"]["base_color"],materials["skin"]["normal"],materials["skin"]["orm"],metallic_factor=0,roughness_factor=1,semantic_role="body-and-face"),
        SkinnedMaterialPrimitive(outfit,undersuit_uv,undersuit_weights,"Kettlejack_v3_Patched_Outfit",materials["outfit"]["base_color"],materials["outfit"]["normal"],materials["outfit"]["orm"],metallic_factor=0,roughness_factor=1,double_sided=True,semantic_role="patched-work-clothes"),
    ]
    rows=_v3_accessories(scaled_landmarks,body)
    grouped=_group_accessories(rows)
    accessory_evidence=[]
    for mesh,joint_name,family,role in grouped:
        uv=box_project_world(mesh,world_units_per_tile=.12)
        uv_report=validate_uv(mesh,uv)
        topo=topology_report(mesh)
        if uv_report["status"]!="pass" or topo["invalid_indices"] or topo["degenerate_faces"]:
            raise ValueError(f"v0.3 accessory invalid: {role}")
        joint=name_to_index[joint_name]
        primitives.append(SkinnedMaterialPrimitive(
            mesh,uv,rigid_skin_weights(mesh,joint),f"Kettlejack_v3_{family}_{joint_name}",
            materials[family]["base_color"],materials[family]["normal"],materials[family]["orm"],
            metallic_factor=metallic[family],roughness_factor=1,semantic_role=role,
        ))
        accessory_evidence.append({"mesh":mesh.name,"joint":joint_name,"joint_index":joint,"material_family":family,"semantic_role":role,"topology":topo,"uv":uv_report})

    clips=build_kettlejack_clips_v3(name_to_index)
    clip_evidence=[]
    for clip in clips:
        report=validate_animation_clip(clip,scaled_skeleton)
        if report["status"]!="pass":
            raise ValueError(f"invalid v0.3 clip {clip.name}: {report}")
        clip_evidence.append({"name":clip.name,**report})
    delivery=write_skinned_multi_gltf(primitives,scaled_skeleton,root,clips,name=ASSET_NAME)

    roles=" ".join(row["semantic_role"] for row in accessory_evidence)
    required=("face-eye","face-brow","face-nose","face-mouth","forehead-goggle","layered-vest","rolled-sleeve","baggy-trouser","kettle-pack","mechanical-leg","heavy-work-boot","wrench-fixed-jaw","wrench-moving-jaw")
    package={
        "schema":SCHEMA,"asset_id":"kettlejack","asset_name":"Kettlejack","candidate_role":"second_render_rehearsed_animated_game_character",
        "design_intent":DESIGN_INTENT,"height_m":actual_height,"ground_y_m":grounded_lo[1],
        "source":{"substrate":"seed_data/hm08_full_body_v0.1","identity_target_state":target_state,"canonical_source_mutated":False},
        "stylization":stylization,"rig":rig_evidence,"skin":skin_evidence,
        "outfit":{"construction":undersuit_evidence,"skin":undersuit_skin_evidence,"offset_m":.0055},
        "clips":clip_evidence,"accessories":accessory_evidence,"materials":materials,"delivery":delivery,
        "render_findings_addressed":["mask-like face","skin-tight clothing","weak face landmarks","fork-like wrench","conservative poses"],
        "acceptance":{
            "target_height_grounded":abs(actual_height-target_height_m)<=1e-9 and abs(grounded_lo[1])<=1e-9,
            "skeleton_valid":validate_skeleton(scaled_skeleton)["status"]=="pass",
            "five_authored_clips":len(clips)==5,
            "multi_material_character":delivery["primitive_count"]>=14,
            "structural_gltf":delivery["validation"]["status"]=="pass",
            "required_visual_semantics_present":all(token in roles for token in required),
        },
        "truth":{
            "real_3d_geometry":True,"real_skeleton":True,"real_skin_weights":True,"real_animation_tracks":True,
            "real_multi_material_gltf":True,"render_review_required":True,"concept_pixel_faithful":False,
            "visual_match_proven":False,"production_deformation_proven":False,"facial_animation_proven":False,
            "automatic_genome_mutation":False,"automatic_release":False,"automatic_canon":False,
        },
    }
    if not all(package["acceptance"].values()):
        raise ValueError(f"Kettlejack v0.3 acceptance failed: {package['acceptance']}")
    files={}
    for path in sorted(root.rglob("*")):
        if path.is_file() and path.name!="kettlejack-v3-package.json":
            files[path.relative_to(root).as_posix()]={"bytes":path.stat().st_size,"sha256":_sha(path.read_bytes())}
    package["files"]=files
    payload=(json.dumps(package,indent=2,sort_keys=True)+"\n").encode()
    (root/"kettlejack-v3-package.json").write_bytes(payload)
    package["package_sha256"]=_sha(payload)
    return package


def main()->int:
    import argparse
    p=argparse.ArgumentParser()
    p.add_argument("output");p.add_argument("--texture-size",type=int,default=64);p.add_argument("--height",type=float,default=TARGET_HEIGHT_M)
    a=p.parse_args()
    package=write_kettlejack_v3_package(a.output,texture_size=a.texture_size,target_height_m=a.height)
    print(json.dumps({"schema":package["schema"],"height_m":package["height_m"],"triangles":package["delivery"]["triangles"],"primitives":package["delivery"]["primitive_count"],"animations":package["delivery"]["animations"],"acceptance":package["acceptance"],"package_sha256":package["package_sha256"]},sort_keys=True))
    return 0

if __name__=="__main__":
    raise SystemExit(main())
