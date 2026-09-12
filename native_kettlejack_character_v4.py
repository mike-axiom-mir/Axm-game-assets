#!/usr/bin/env python3
"""Kettlejack v0.4: third render-driven visual repair pass.

The v0.3 retained Godot renders were inspected before this pass. They proved
structural correctness and improved face/clothing semantics, but still exposed
specific visual failures: the tool covered the centerline, the face still read
as attached discs, the vest was slab-like, the wrench head read as a hammer/fork,
and jump/run lacked enough spatial separation. v0.4 repairs those exact issues.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from native_animation import AnimationClip, AnimationTrack, validate_animation_clip
from native_construction_kit import beam_segment, pipe_path, rounded_box, torus_ring
from native_geometry import bounds, scale, topology_report, translate
from native_hm08_humanoid_rig import build_hm08_humanoid_skeleton, derive_hm08_rig_landmarks
from native_hm08_humanoid_skin_v2 import build_hm08_skin_weights_v2
from native_hm08_undersuit import _load_identity_body, build_hm08_undersuit
from native_kettlejack_character import DESIGN_INTENT, METALLIC_FACTORS, _rot_track, _scale_skeleton, _scaled_point, _write_materials
from native_kettlejack_character_v2 import EXTRA_MATERIAL_RECIPES, _ellipsoid, _extra_materials, _group_accessories, _head_region, stylize_body_v2
from native_kettlejack_character_v3 import _v3_accessories
from native_skin import validate_skeleton
from native_skinned_multi_gltf import SkinnedMaterialPrimitive, rigid_skin_weights, write_skinned_multi_gltf
from native_uv import box_project_world, validate_uv

SCHEMA = "axm.game-assets.kettlejack-character/v0.4"
ASSET_NAME = "kettlejack_game_character_v0_4"
TARGET_HEIGHT_M = 1.30


def _sha(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _lerp(a, b, t: float):
    return tuple(a[i] + (b[i] - a[i]) * t for i in range(3))


def _translation_track(index: int, times: list[float], values: list[tuple[float, float, float]]) -> AnimationTrack:
    return AnimationTrack(index, "translation", times, values)


def _base_rows(landmarks, body):
    rows = _v3_accessories(landmarks, body)
    banned = (
        "face-eye", "face-pupil", "face-brow", "face-nose", "face-mouth",
        "forehead-goggle", "layered-vest", "harness-strap", "rolled-sleeve",
        "baggy-trouser", "fingerless-glove", "repaired-chest-patch",
        "wrench-staff", "wrench-grip", "wrench-head", "wrench-fixed-jaw",
        "wrench-moving-jaw", "wrench-thumbwheel",
    )
    return [row for row in rows if not any(token in row[3] for token in banned)]


def _v4_accessories(landmarks, body):
    rows = list(_base_rows(landmarks, body))
    lo, hi = bounds(body)
    hb = _head_region(body)
    chest = landmarks["chest"]
    pelvis = landmarks["pelvis"]
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

    # Face: smaller eyes recessed into the head, explicit friendly smile, nose,
    # brows, and a cap/goggle stack that stays above the eyes.
    eye_y = hb["min_y"] + hb["height"] * .46
    front_z = hb["max_z"]
    eye_dx = hb["width"] * .175
    eye_r = max(.018, hb["width"] * .072)
    for side, sx in (("left", -1.0), ("right", 1.0)):
        cx = sx * eye_dx
        rows.append((_ellipsoid(
            f"kettlejack-v4-eye-{side}", (cx, eye_y, front_z-eye_r*.42),
            (eye_r, eye_r*1.12, eye_r*.48), segments=22, rings=11,
        ), "head", "eye_white", "face-eye-recessed"))
        rows.append((_ellipsoid(
            f"kettlejack-v4-pupil-{side}", (cx, eye_y, front_z+eye_r*.02),
            (eye_r*.30, eye_r*.38, eye_r*.12), segments=16, rings=8,
        ), "head", "eye_dark", "face-pupil"))
        brow_y = eye_y + eye_r*1.45
        if sx < 0:
            a=(cx-eye_r*.58,brow_y,front_z+.005); b=(cx+eye_r*.56,brow_y+eye_r*.11,front_z+.005)
        else:
            a=(cx-eye_r*.56,brow_y+eye_r*.11,front_z+.005); b=(cx+eye_r*.58,brow_y,front_z+.005)
        rows.append((beam_segment(a,b,width=.007,depth=.005,name=f"kettlejack-v4-brow-{side}"),"head","hair","face-brow"))

    rows.append((_ellipsoid(
        "kettlejack-v4-nose", (0.0, eye_y-eye_r*.62, front_z+.010),
        (eye_r*.42, eye_r*.52, eye_r*.34), segments=16, rings=8,
    ), "head", "skin", "face-nose"))
    mouth_y = eye_y-eye_r*1.72
    rows.append((rounded_box(
        (0.0,mouth_y+.004,front_z+.007),(eye_r*1.38,eye_r*.48,.010),chamfer=.006,name="kettlejack-v4-teeth"
    ),"head","eye_white","face-smile-teeth"))
    rows.append((beam_segment(
        (-eye_r*.76,mouth_y+eye_r*.10,front_z+.014),(0.0,mouth_y-eye_r*.10,front_z+.014),width=.006,depth=.004,name="kettlejack-v4-smile-left"
    ),"head","eye_dark","face-smile-line"))
    rows.append((beam_segment(
        (0.0,mouth_y-eye_r*.10,front_z+.014),(eye_r*.76,mouth_y+eye_r*.10,front_z+.014),width=.006,depth=.004,name="kettlejack-v4-smile-right"
    ),"head","eye_dark","face-smile-line"))

    cap_center_z=(hb["min_z"]+hb["max_z"])*.5-.012
    rows.append((_ellipsoid(
        "kettlejack-v4-pilot-cap", (0.0,hb["max_y"]-.018,cap_center_z),
        (hb["width"]*.38,hb["height"]*.18,hb["depth"]*.40), segments=22, rings=10,
    ),"head","wood","pilot-cap"))
    goggle_y=hb["max_y"]-hb["height"]*.14
    goggle_z=front_z+.008
    goggle_r=eye_r*.86
    for side,sx in (("left",-1.0),("right",1.0)):
        rows.append((torus_ring(
            (sx*eye_dx,goggle_y,goggle_z),radius=goggle_r,tube=max(.005,goggle_r*.18),axis="z",
            major_segments=18,minor_segments=5,name=f"kettlejack-v4-goggle-{side}"
        ),"head","steel","forehead-goggle-rim"))
    rows.append((beam_segment(
        (-goggle_r*.25,goggle_y,goggle_z),(goggle_r*.25,goggle_y,goggle_z),width=.007,depth=.006,name="kettlejack-v4-goggle-bridge"
    ),"head","steel","forehead-goggle-bridge"))

    # Clothing: remove v0.3's rectangular slabs. Use thinner vest plates plus
    # round upper-arm sleeves and cargo-thigh shells so the silhouette has volume
    # without becoming box armour.
    rows.append((rounded_box(
        (-.062,chest[1]-.085,hi[2]+.012),(.095,.225,.028),chamfer=.014,name="kettlejack-v4-vest-left"
    ),"chest","outfit","layered-vest-panel"))
    rows.append((rounded_box(
        (.062,chest[1]-.085,hi[2]+.012),(.095,.225,.028),chamfer=.014,name="kettlejack-v4-vest-right"
    ),"chest","outfit","layered-vest-panel"))
    rows.append((beam_segment(
        (-.070,chest[1]+.030,hi[2]+.030),(-.105,pelvis[1]+.052,hi[2]+.032),width=.022,depth=.012,name="kettlejack-v4-harness-left"
    ),"chest","wood","harness-strap"))
    rows.append((beam_segment(
        (.070,chest[1]+.030,hi[2]+.030),(.105,pelvis[1]+.052,hi[2]+.032),width=.022,depth=.012,name="kettlejack-v4-harness-right"
    ),"chest","wood","harness-strap"))

    for joint,a,b in (("left_upper_arm",left_upper,left_fore),("right_upper_arm",right_upper,right_fore)):
        end=_lerp(a,b,.58)
        rows.append((pipe_path((a,end),radius=.064,sides=12,name=f"kettlejack-v4-{joint}-sleeve"),joint,"outfit","rolled-sleeve"))
    for joint,a,b in (("left_thigh",left_thigh,left_shin),("right_thigh",right_thigh,right_shin)):
        end=_lerp(a,b,.66)
        rows.append((pipe_path((a,end),radius=.092,sides=12,name=f"kettlejack-v4-{joint}-cargo"),joint,"outfit","baggy-trouser-thigh"))
    for joint,p in (("left_hand",left_hand),("right_hand",right_hand)):
        rows.append((rounded_box((p[0],p[1]-.010,p[2]),(.078,.064,.066),chamfer=.018,name=f"kettlejack-v4-{joint}-glove"),joint,"rubber","fingerless-glove"))

    # Asymmetrical front repairs keep it from reading like a uniform body suit.
    rows.append((rounded_box(
        (-.066,chest[1]-.120,hi[2]+.032),(.065,.082,.011),chamfer=.005,name="kettlejack-v4-chest-patch"
    ),"chest","ivory_metal","repaired-chest-patch"))
    rows.append((rounded_box(
        (.115,pelvis[1]-.005,hi[2]+.030),(.060,.080,.035),chamfer=.010,name="kettlejack-v4-side-pouch"
    ),"pelvis","wood","side-tool-pouch"))

    # Wrench: place the shaft clearly to the character's right in bind pose so
    # it no longer blocks the face in every review angle. The head is asymmetric
    # like an adjustable wrench: long fixed jaw, shorter moving jaw + thumbwheel.
    wx,_wy,wz=right_hand
    tool_x=wx+.145
    tool_z=wz+.060
    shaft_bottom=.045
    shaft_top=min(hi[1]+.095,1.39)
    rows.append((beam_segment(
        (tool_x,shaft_bottom,tool_z),(tool_x,shaft_top,tool_z),width=.045,depth=.040,name="kettlejack-v4-wrench-shaft"
    ),"right_hand","rust_red","wrench-staff-shaft"))
    for idx,y in enumerate((.22,.285,.35)):
        rows.append((torus_ring((tool_x,y,tool_z),radius=.030,tube=.005,axis="y",major_segments=14,minor_segments=5,name=f"kettlejack-v4-wrap-{idx}"),"right_hand","scarf","wrench-grip-wrap"))
    head_y=shaft_top+.018
    rows.append((rounded_box(
        (tool_x-.030,head_y,tool_z),(.220,.064,.052),chamfer=.014,name="kettlejack-v4-wrench-head-base"
    ),"right_hand","steel","wrench-head-base"))
    rows.append((beam_segment(
        (tool_x-.118,head_y+.010,tool_z),(tool_x-.168,head_y+.145,tool_z),width=.055,depth=.048,name="kettlejack-v4-fixed-jaw"
    ),"right_hand","rust_red","wrench-fixed-jaw"))
    rows.append((beam_segment(
        (tool_x+.022,head_y+.008,tool_z),(tool_x+.060,head_y+.105,tool_z),width=.046,depth=.044,name="kettlejack-v4-moving-jaw"
    ),"right_hand","rust_red","wrench-moving-jaw"))
    rows.append((torus_ring(
        (tool_x+.010,head_y+.020,tool_z+.030),radius=.022,tube=.007,axis="z",major_segments=14,minor_segments=5,name="kettlejack-v4-thumbwheel"
    ),"right_hand","yellow_metal","wrench-thumbwheel"))
    return rows


def build_clips_v4(name_to_index: dict[str,int], skeleton) -> tuple[AnimationClip,...]:
    root=name_to_index["root"]
    root_base=tuple(float(v) for v in skeleton.joints[root].translation)
    def root_values(deltas):
        return [(root_base[0],root_base[1]+dy,root_base[2]) for dy in deltas]

    idle_t=[0.0,.8,1.6]
    idle=AnimationClip("idle",[
        _rot_track(name_to_index["left_upper_arm"],idle_t,[{"z":50},{"z":54},{"z":50}]),
        _rot_track(name_to_index["right_upper_arm"],idle_t,[{"z":-52},{"z":-56},{"z":-52}]),
        _rot_track(name_to_index["right_forearm"],idle_t,[{"z":-22},{"z":-18},{"z":-22}]),
        _rot_track(name_to_index["right_hand"],idle_t,[{"z":68},{"z":72},{"z":68}]),
        _rot_track(name_to_index["head"],idle_t,[{"y":-4},{"y":5},{"y":-4}]),
        _translation_track(root,idle_t,root_values([0,.010,0])),
    ])

    run_t=[0.0,.18,.36,.54,.72]
    run=AnimationClip("run",[
        _rot_track(name_to_index["left_thigh"],run_t,[{"x":-44},{"x":0},{"x":44},{"x":0},{"x":-44}]),
        _rot_track(name_to_index["right_thigh"],run_t,[{"x":44},{"x":0},{"x":-44},{"x":0},{"x":44}]),
        _rot_track(name_to_index["left_shin"],run_t,[{"x":60},{"x":22},{"x":-14},{"x":22},{"x":60}]),
        _rot_track(name_to_index["right_shin"],run_t,[{"x":-14},{"x":22},{"x":60},{"x":22},{"x":-14}]),
        _rot_track(name_to_index["left_upper_arm"],run_t,[{"x":34,"z":54},{"z":54},{"x":-34,"z":54},{"z":54},{"x":34,"z":54}]),
        _rot_track(name_to_index["right_upper_arm"],run_t,[{"x":-28,"z":-54},{"z":-54},{"x":28,"z":-54},{"z":-54},{"x":-28,"z":-54}]),
        _rot_track(name_to_index["right_hand"],run_t,[{"z":54},{"z":58},{"z":48},{"z":58},{"z":54}]),
        _rot_track(name_to_index["spine_mid"],run_t,[{"x":-15,"y":-8},{"x":-11},{"x":-15,"y":8},{"x":-11},{"x":-15,"y":-8}]),
        _translation_track(root,run_t,root_values([0,.024,0,.024,0])),
    ])

    jump_t=[0.0,.22,.46,.76]
    jump=AnimationClip("jump",[
        _rot_track(name_to_index["left_thigh"],jump_t,[{"x":10},{"x":-48},{"x":24},{"x":8}]),
        _rot_track(name_to_index["right_thigh"],jump_t,[{"x":-8},{"x":-32},{"x":48},{"x":-8}]),
        _rot_track(name_to_index["left_shin"],jump_t,[{"x":10},{"x":72},{"x":34},{"x":8}]),
        _rot_track(name_to_index["right_shin"],jump_t,[{"x":8},{"x":58},{"x":72},{"x":8}]),
        _rot_track(name_to_index["left_upper_arm"],jump_t,[{"z":54},{"z":112},{"z":92},{"z":54}]),
        _rot_track(name_to_index["right_upper_arm"],jump_t,[{"z":-54},{"z":-98},{"z":-82},{"z":-54}]),
        _rot_track(name_to_index["right_hand"],jump_t,[{"z":66},{"z":94},{"z":82},{"z":66}]),
        _translation_track(root,jump_t,root_values([0,.18,.29,0])),
    ])

    attack_t=[0.0,.16,.34,.58,.84]
    attack=AnimationClip("wrench_swing",[
        _rot_track(name_to_index["right_upper_arm"],attack_t,[{"y":45,"z":-52},{"y":82,"z":-24},{"y":-72,"z":-12},{"y":-96,"z":-46},{"y":45,"z":-52}]),
        _rot_track(name_to_index["right_forearm"],attack_t,[{"y":22,"z":-24},{"y":52,"z":-8},{"y":-40,"z":-42},{"y":-20,"z":-22},{"y":22,"z":-24}]),
        _rot_track(name_to_index["right_hand"],attack_t,[{"z":60},{"z":32},{"z":-26},{"z":16},{"z":60}]),
        _rot_track(name_to_index["chest"],attack_t,[{"x":-5,"y":-16},{"x":-8,"y":-34},{"x":8,"y":42},{"x":4,"y":28},{"x":-5,"y":-16}]),
        _rot_track(name_to_index["left_upper_arm"],attack_t,[{"z":56},{"z":76},{"z":40},{"z":48},{"z":56}]),
        _translation_track(root,attack_t,root_values([0,.015,.020,.010,0])),
    ])

    victory_t=[0.0,.30,.66,1.02]
    victory=AnimationClip("victory",[
        _rot_track(name_to_index["left_upper_arm"],victory_t,[{"z":54},{"z":92},{"z":78},{"z":54}]),
        _rot_track(name_to_index["left_forearm"],victory_t,[{"z":18},{"z":-76},{"z":-50},{"z":18}]),
        _rot_track(name_to_index["right_upper_arm"],victory_t,[{"z":-54},{"z":-96},{"z":-82},{"z":-54}]),
        _rot_track(name_to_index["right_forearm"],victory_t,[{"z":-24},{"z":78},{"z":56},{"z":-24}]),
        _rot_track(name_to_index["right_hand"],victory_t,[{"z":68},{"z":102},{"z":90},{"z":68}]),
        _rot_track(name_to_index["right_shin"],victory_t,[{"x":0},{"x":64},{"x":36},{"x":0}]),
        _rot_track(name_to_index["head"],victory_t,[{"y":0},{"x":-8,"y":-12},{"x":-4,"y":10},{"y":0}]),
        _translation_track(root,victory_t,root_values([0,.045,.018,0])),
    ])
    return idle,run,jump,attack,victory


def write_kettlejack_v4_package(output: str|Path, *, texture_size: int=64, target_height_m: float=TARGET_HEIGHT_M) -> dict[str,Any]:
    root=Path(output)
    root.mkdir(parents=True,exist_ok=True)
    if any(root.iterdir()):
        raise FileExistsError(f"Kettlejack v0.4 output must start empty: {root}")

    source_body,body_uv,target_state=_load_identity_body()
    styled,stylization=stylize_body_v2(source_body)
    if validate_uv(styled,body_uv)["status"]!="pass":
        raise ValueError("stylized body UV invalid")
    skeleton,rig_evidence,name_to_index=build_hm08_humanoid_skeleton(styled)
    landmarks=derive_hm08_rig_landmarks(styled)
    body_weights,skin_evidence=build_hm08_skin_weights_v2(styled,skeleton,landmarks,name_to_index)
    undersuit,undersuit_uv,undersuit_evidence=build_hm08_undersuit(styled,body_uv,offset_m=.0050)
    undersuit_weights,undersuit_skin_evidence=build_hm08_skin_weights_v2(undersuit,skeleton,landmarks,name_to_index)

    lo,hi=bounds(styled)
    factor=target_height_m/(hi[1]-lo[1])
    scaled_body=scale(styled,factor,name="kettlejack-v4-body")
    scaled_outfit=scale(undersuit,factor,name="kettlejack-v4-outfit")
    scaled_lo,_=bounds(scaled_body)
    ground_offset=-scaled_lo[1]
    body=translate(scaled_body,(0,ground_offset,0),name="kettlejack-v4-body")
    outfit=translate(scaled_outfit,(0,ground_offset,0),name="kettlejack-v4-outfit")
    scaled_skeleton=_scale_skeleton(skeleton,factor,ground_offset)
    scaled_landmarks={name:_scaled_point(point,factor,ground_offset) for name,point in landmarks.items()}
    grounded_lo,grounded_hi=bounds(body)
    actual_height=grounded_hi[1]-grounded_lo[1]

    materials=_write_materials(root,texture_size)
    _extra_materials(root,texture_size,materials)
    metallic={**METALLIC_FACTORS,**{name:float(recipe["metallic"]) for name,recipe in EXTRA_MATERIAL_RECIPES.items()}}

    primitives=[
        SkinnedMaterialPrimitive(body,body_uv,body_weights,"Kettlejack_v4_Skin",materials["skin"]["base_color"],materials["skin"]["normal"],materials["skin"]["orm"],metallic_factor=0,roughness_factor=1,semantic_role="body-and-face"),
        SkinnedMaterialPrimitive(outfit,undersuit_uv,undersuit_weights,"Kettlejack_v4_Patched_Outfit",materials["outfit"]["base_color"],materials["outfit"]["normal"],materials["outfit"]["orm"],metallic_factor=0,roughness_factor=1,double_sided=True,semantic_role="patched-work-clothes"),
    ]
    grouped=_group_accessories(_v4_accessories(scaled_landmarks,body))
    accessory_evidence=[]
    for mesh,joint_name,family,role in grouped:
        uv=box_project_world(mesh,world_units_per_tile=.12)
        uv_report=validate_uv(mesh,uv)
        topo=topology_report(mesh)
        if uv_report["status"]!="pass" or topo["invalid_indices"] or topo["degenerate_faces"]:
            raise ValueError(f"invalid v0.4 accessory {role}")
        joint=name_to_index[joint_name]
        primitives.append(SkinnedMaterialPrimitive(mesh,uv,rigid_skin_weights(mesh,joint),f"Kettlejack_v4_{family}_{joint_name}",materials[family]["base_color"],materials[family]["normal"],materials[family]["orm"],metallic_factor=metallic[family],roughness_factor=1,semantic_role=role))
        accessory_evidence.append({"mesh":mesh.name,"joint":joint_name,"joint_index":joint,"material_family":family,"semantic_role":role,"topology":topo,"uv":uv_report})

    clips=build_clips_v4(name_to_index,scaled_skeleton)
    clip_evidence=[]
    for clip in clips:
        report=validate_animation_clip(clip,scaled_skeleton)
        if report["status"]!="pass":
            raise ValueError(f"invalid v0.4 clip {clip.name}: {report}")
        clip_evidence.append({"name":clip.name,**report})
    delivery=write_skinned_multi_gltf(primitives,scaled_skeleton,root,clips,name=ASSET_NAME)

    roles=" ".join(row["semantic_role"] for row in accessory_evidence)
    required=("face-eye-recessed","face-smile","pilot-cap","forehead-goggle","layered-vest-panel","rolled-sleeve","baggy-trouser","kettle-pack","mechanical-leg","heavy-work-boot","wrench-fixed-jaw","wrench-moving-jaw")
    package={
        "schema":SCHEMA,"asset_id":"kettlejack","asset_name":"Kettlejack","candidate_role":"third_render_rehearsed_animated_game_character",
        "design_intent":DESIGN_INTENT,"height_m":actual_height,"ground_y_m":grounded_lo[1],
        "source":{"substrate":"seed_data/hm08_full_body_v0.1","identity_target_state":target_state,"canonical_source_mutated":False},
        "stylization":stylization,"rig":rig_evidence,"skin":skin_evidence,"outfit":{"construction":undersuit_evidence,"skin":undersuit_skin_evidence,"offset_m":.0050},
        "clips":clip_evidence,"accessories":accessory_evidence,"materials":materials,"delivery":delivery,
        "render_findings_addressed":["centerline-obscuring staff","disc-like eyes","slab vest","hammer/fork wrench head","weak jump/run spatial separation"],
        "acceptance":{
            "target_height_grounded":abs(actual_height-target_height_m)<=1e-9 and abs(grounded_lo[1])<=1e-9,
            "skeleton_valid":validate_skeleton(scaled_skeleton)["status"]=="pass",
            "five_authored_clips":len(clips)==5,
            "multi_material_character":delivery["primitive_count"]>=14,
            "structural_gltf":delivery["validation"]["status"]=="pass",
            "required_visual_semantics_present":all(token in roles for token in required),
        },
        "truth":{
            "real_3d_geometry":True,"real_skeleton":True,"real_skin_weights":True,"real_animation_tracks":True,"real_multi_material_gltf":True,
            "render_review_required":True,"concept_pixel_faithful":False,"visual_match_proven":False,"production_deformation_proven":False,"facial_animation_proven":False,
            "automatic_genome_mutation":False,"automatic_release":False,"automatic_canon":False,
        },
    }
    if not all(package["acceptance"].values()):
        raise ValueError(f"Kettlejack v0.4 acceptance failed: {package['acceptance']}")
    files={}
    for path in sorted(root.rglob("*")):
        if path.is_file() and path.name!="kettlejack-v4-package.json":
            files[path.relative_to(root).as_posix()]={"bytes":path.stat().st_size,"sha256":_sha(path.read_bytes())}
    package["files"]=files
    payload=(json.dumps(package,indent=2,sort_keys=True)+"\n").encode()
    (root/"kettlejack-v4-package.json").write_bytes(payload)
    package["package_sha256"]=_sha(payload)
    return package


def main()->int:
    import argparse
    p=argparse.ArgumentParser();p.add_argument("output");p.add_argument("--texture-size",type=int,default=64);p.add_argument("--height",type=float,default=TARGET_HEIGHT_M)
    a=p.parse_args();package=write_kettlejack_v4_package(a.output,texture_size=a.texture_size,target_height_m=a.height)
    print(json.dumps({"schema":package["schema"],"height_m":package["height_m"],"triangles":package["delivery"]["triangles"],"primitives":package["delivery"]["primitive_count"],"animations":package["delivery"]["animations"],"acceptance":package["acceptance"],"package_sha256":package["package_sha256"]},sort_keys=True))
    return 0

if __name__=="__main__":
    raise SystemExit(main())
