#!/usr/bin/env python3
"""Rifle contact v0.5: preserve v0.4 arm/contact state and close finger chains.

Run 2 proved the human-scale rifle, two-hand socket contact, shared 23-joint arm
pose and bone-segment arm skin. It also pinned a source-grounded 53-joint rig
with 30 finger pivots and finger-local skin weights. This module combines those
truths without changing the rifle or arm solution.

The grip is a bounded proposal: deterministic finger flexion candidates are
chosen only by whether source-grounded fingertips move closer to the already
proven weapon grip socket. Real Godot hand close-ups remain the promotion gate.
"""
from __future__ import annotations

import copy
from dataclasses import replace
from math import cos, radians, sin, sqrt

from native_geometry import Mesh, bounds
from native_hm08_finger_rig import (
    _finger_rows,
    _source_side_mapping,
    build_hm08_finger_skeleton,
    build_hm08_finger_skin_weights,
    load_finger_landmarks,
)
from native_hm08_rifle_contact_pose import _centroid, _distance, _quat_mul
from native_hm08_rifle_contact_pose_v2 import derive_shared_rig_arms
from native_hm08_rifle_contact_pose_v4 import build_segment_skin_rifle_contact_pose
from native_hm08_undersuit import _load_identity_body
from native_skin import Joint, Quat, Skeleton, global_joint_matrices, normalize_quaternion, skin_vertices, transform_point, validate_skeleton

SCHEMA = "axm.game-assets.hm08-rifle-contact-pose.v0.5"


def _sub(a, b):
    return a[0]-b[0], a[1]-b[1], a[2]-b[2]


def _add(a, b):
    return a[0]+b[0], a[1]+b[1], a[2]+b[2]


def _mul(a, scalar: float):
    return a[0]*scalar, a[1]*scalar, a[2]*scalar


def _dot(a, b) -> float:
    return a[0]*b[0]+a[1]*b[1]+a[2]*b[2]


def _cross(a, b):
    return (
        a[1]*b[2]-a[2]*b[1],
        a[2]*b[0]-a[0]*b[2],
        a[0]*b[1]-a[1]*b[0],
    )


def _length(a) -> float:
    return sqrt(_dot(a,a))


def _normalize(a):
    length=_length(a)
    if length<=1e-12:
        raise ValueError("cannot normalize zero grip axis")
    return a[0]/length,a[1]/length,a[2]/length


def _axis_angle(axis, degrees: float) -> Quat:
    axis=_normalize(axis)
    half=radians(degrees)*0.5
    s=sin(half)
    return normalize_quaternion((axis[0]*s,axis[1]*s,axis[2]*s,cos(half)))


def _mean(points):
    if not points:
        raise ValueError("mean requires points")
    inv=1.0/len(points)
    return tuple(sum(point[axis] for point in points)*inv for axis in range(3))


def _tip_world(skeleton: Skeleton, indices: dict[str,int], rig_evidence: dict[str,object], side: str, digit: int):
    globals_=global_joint_matrices(skeleton)
    joint=indices[f"{side}_finger{digit}_3"]
    offset=tuple(float(v) for v in rig_evidence["tip_local_offsets"][f"{side}_finger{digit}_tip"])
    return transform_point(globals_[joint],offset)


def _tip_distances(skeleton: Skeleton, indices: dict[str,int], rig_evidence: dict[str,object], side: str, socket):
    return {digit:_distance(_tip_world(skeleton,indices,rig_evidence,side,digit),socket) for digit in range(1,6)}


def _mean_digits(distances: dict[int,float], digits) -> float:
    rows=[distances[digit] for digit in digits]
    return sum(rows)/len(rows)


def _finger_axes(packet: dict[str,object], side: str):
    mapping=_source_side_mapping(packet)
    rows=_finger_rows(packet,mapping)
    base2=tuple(float(v) for v in rows[(side,2,1)]["head_m"])
    base5=tuple(float(v) for v in rows[(side,5,1)]["head_m"])
    spread=_normalize(_sub(base5,base2))

    nonthumb_forward=[]
    for digit in range(2,6):
        row=rows[(side,digit,1)]
        head=tuple(float(v) for v in row["head_m"])
        tail=tuple(float(v) for v in row["tail_m"])
        nonthumb_forward.append(_normalize(_sub(tail,head)))
    forward=_normalize(_mean(nonthumb_forward))
    # Remove any forward component so the bend axis remains across the knuckles.
    spread=_sub(spread,_mul(forward,_dot(spread,forward)))
    spread=_normalize(spread)

    thumb=rows[(side,1,1)]
    thumb_head=tuple(float(v) for v in thumb["head_m"])
    thumb_tail=tuple(float(v) for v in thumb["tail_m"])
    thumb_forward=_normalize(_sub(thumb_tail,thumb_head))
    index_target=_normalize(_sub(base2,thumb_head))
    thumb_axis=_cross(thumb_forward,index_target)
    if _length(thumb_axis)<=1e-8:
        thumb_axis=spread
    else:
        thumb_axis=_normalize(thumb_axis)
    return {"nonthumb":spread,"thumb":thumb_axis,"source_mapping":mapping}


def _apply_side_curl(
    skeleton: Skeleton,
    indices: dict[str,int],
    side: str,
    *,
    nonthumb_axis,
    nonthumb_sign: float,
    nonthumb_scale: float,
    thumb_axis,
    thumb_sign: float,
    thumb_scale: float,
) -> Skeleton:
    joints=list(skeleton.joints)
    nonthumb_angles={1:48.0,2:62.0,3:42.0}
    thumb_angles={1:30.0,2:42.0,3:28.0}
    for digit in range(1,6):
        for segment in range(1,4):
            name=f"{side}_finger{digit}_{segment}"
            index=indices[name]
            source=joints[index]
            if digit==1:
                q=_axis_angle(thumb_axis,thumb_sign*thumb_scale*thumb_angles[segment])
            else:
                q=_axis_angle(nonthumb_axis,nonthumb_sign*nonthumb_scale*nonthumb_angles[segment])
            joints[index]=replace(source,rotation=_quat_mul(source.rotation,q))
    result=Skeleton(joints)
    report=validate_skeleton(result)
    if report["status"]!="pass":
        raise ValueError(f"finger curl produced invalid skeleton: {report}")
    return result


def _apply_nonthumb_only(skeleton: Skeleton,indices:dict[str,int],side:str,axis,sign:float,scale:float)->Skeleton:
    joints=list(skeleton.joints)
    angles={1:48.0,2:62.0,3:42.0}
    for digit in range(2,6):
        for segment in range(1,4):
            index=indices[f"{side}_finger{digit}_{segment}"]
            source=joints[index]
            joints[index]=replace(source,rotation=_quat_mul(source.rotation,_axis_angle(axis,sign*scale*angles[segment])))
    result=Skeleton(joints)
    if validate_skeleton(result)["status"]!="pass":raise ValueError("nonthumb candidate invalid")
    return result


def _apply_thumb_only(skeleton: Skeleton,indices:dict[str,int],side:str,axis,sign:float,scale:float)->Skeleton:
    joints=list(skeleton.joints)
    angles={1:30.0,2:42.0,3:28.0}
    for segment in range(1,4):
        index=indices[f"{side}_finger1_{segment}"]
        source=joints[index]
        joints[index]=replace(source,rotation=_quat_mul(source.rotation,_axis_angle(axis,sign*scale*angles[segment])))
    result=Skeleton(joints)
    if validate_skeleton(result)["status"]!="pass":raise ValueError("thumb candidate invalid")
    return result


def build_finger_grip_rifle_contact_pose(body_m: Mesh) -> tuple[Mesh,dict[str,object]]:
    v4_mesh,v4=build_segment_skin_rifle_contact_pose(body_m)
    bind,finger_indices,rig_evidence=build_hm08_finger_skeleton(body_m)
    weights,skin_evidence=build_hm08_finger_skin_weights(body_m,bind,finger_indices)
    indices={joint.name:index for index,joint in enumerate(bind.joints)}

    # Reconstruct the exact v0.4 arm/wrist pose on the 53-joint skeleton. The
    # appended finger joints inherit the same hand transform with identity local
    # rotations, so this must reproduce v0.4 before any curl is added.
    arm_joints=list(bind.joints)
    for side in ("right","left"):
        row=v4["pose"][side]
        for suffix,key in (("upper_arm","shoulder_rotation"),("forearm","elbow_rotation"),("hand","hand_rotation")):
            index=indices[f"{side}_{suffix}"]
            source=arm_joints[index]
            arm_joints[index]=replace(source,rotation=tuple(float(v) for v in row[key]))
    open_skeleton=Skeleton(arm_joints)
    open_report=validate_skeleton(open_skeleton)
    if open_report["status"]!="pass":raise ValueError(f"extended open pose invalid: {open_report}")
    open_mesh=Mesh("sentinel_hm08_finger_rig_open_contact_v0_5",skin_vertices(body_m,weights,bind,open_skeleton),list(body_m.faces))
    open_vs_v4=max(_distance(a,b) for a,b in zip(open_mesh.vertices,v4_mesh.vertices))

    packet=load_finger_landmarks()
    axes={side:_finger_axes(packet,side) for side in ("right","left")}
    sockets={
        "right":tuple(float(v) for v in v4["contact"]["primary_hand_contact_world_position"]),
        "left":tuple(float(v) for v in v4["contact"]["support_hand_contact_world_position"]),
    }
    choices={}
    current=open_skeleton
    for side in ("right","left"):
        open_dist=_tip_distances(current,indices,rig_evidence,side,sockets[side])
        nonthumb_candidates=[]
        for sign in (-1.0,1.0):
            for scale in (0.72,0.90,1.08):
                candidate=_apply_nonthumb_only(current,indices,side,axes[side]["nonthumb"],sign,scale)
                distances=_tip_distances(candidate,indices,rig_evidence,side,sockets[side])
                score=_mean_digits(distances,(2,3,4,5))
                nonthumb_candidates.append((score,sign,scale,candidate,distances))
        nonthumb_candidates.sort(key=lambda row:(row[0],row[1],row[2]))
        nonthumb_score,nonthumb_sign,nonthumb_scale,nonthumb_skeleton,nonthumb_dist=nonthumb_candidates[0]

        thumb_candidates=[]
        for sign in (-1.0,1.0):
            for scale in (0.65,0.85,1.05):
                candidate=_apply_thumb_only(nonthumb_skeleton,indices,side,axes[side]["thumb"],sign,scale)
                distances=_tip_distances(candidate,indices,rig_evidence,side,sockets[side])
                thumb_candidates.append((distances[1],sign,scale,candidate,distances))
        thumb_candidates.sort(key=lambda row:(row[0],row[1],row[2]))
        thumb_score,thumb_sign,thumb_scale,current,curled_dist=thumb_candidates[0]
        choices[side]={
            "socket_world":list(sockets[side]),
            "source_side":axes[side]["source_mapping"][side],
            "nonthumb_axis_bind":list(axes[side]["nonthumb"]),
            "thumb_axis_bind":list(axes[side]["thumb"]),
            "nonthumb_sign":nonthumb_sign,
            "nonthumb_scale":nonthumb_scale,
            "thumb_sign":thumb_sign,
            "thumb_scale":thumb_scale,
            "open_tip_distance_m":{str(k):v for k,v in open_dist.items()},
            "curled_tip_distance_m":{str(k):v for k,v in curled_dist.items()},
            "open_nonthumb_mean_m":_mean_digits(open_dist,(2,3,4,5)),
            "curled_nonthumb_mean_m":_mean_digits(curled_dist,(2,3,4,5)),
            "open_thumb_m":open_dist[1],
            "curled_thumb_m":curled_dist[1],
        }

    posed=current
    posed_report=validate_skeleton(posed)
    if posed_report["status"]!="pass":raise ValueError(f"v0.5 posed skeleton invalid: {posed_report}")
    posed_mesh=Mesh("sentinel_hm08_finger_grip_rifle_contact_v0_5",skin_vertices(body_m,weights,bind,posed),list(body_m.faces))

    finger_joint_set=set(finger_indices.values())
    curl_moved=0
    nonfinger_curl_max=0.0
    finger_curl_max=0.0
    for vertex_index,(before,after) in enumerate(zip(open_mesh.vertices,posed_mesh.vertices)):
        delta=_distance(before,after)
        active=any(joint in finger_joint_set and weight>1e-9 for joint,weight in zip(weights.joints[vertex_index],weights.weights[vertex_index]))
        if active:
            if delta>1e-10:curl_moved+=1
            finger_curl_max=max(finger_curl_max,delta)
        else:
            nonfinger_curl_max=max(nonfinger_curl_max,delta)

    arms=derive_shared_rig_arms(body_m, __import__("native_hm08_humanoid_rig").derive_hm08_humanoid_rig.derive_hm08_rig_landmarks(body_m)) if False else None
    # Hand/finger region evidence comes directly from skin influence rows so no
    # second hand-region classifier can silently disagree with the rig.
    finger_surface={}
    for side in ("right","left"):
        side_joint_set={index for name,index in finger_indices.items() if name.startswith(side+"_")}
        vertex_indices=[
            index for index,(jrow,wrow) in enumerate(zip(weights.joints,weights.weights))
            if any(joint in side_joint_set and weight>1e-9 for joint,weight in zip(jrow,wrow))
        ]
        centroid=_centroid(posed_mesh,vertex_indices)
        finger_surface[side]={
            "vertex_count":len(vertex_indices),
            "centroid":list(centroid),
            "centroid_to_socket_m":_distance(centroid,sockets[side]),
        }

    lo,hi=bounds(body_m);height=hi[1]-lo[1]
    head_indices=[i for i,p in enumerate(body_m.vertices) if p[1]>=lo[1]+height*0.84]
    lower_indices=[i for i,p in enumerate(body_m.vertices) if p[1]<=lo[1]+height*0.50]
    head_curl=max(_distance(open_mesh.vertices[i],posed_mesh.vertices[i]) for i in head_indices)
    lower_curl=max(_distance(open_mesh.vertices[i],posed_mesh.vertices[i]) for i in lower_indices)

    acceptance={
        "finger_rig_53_joints":len(bind.joints)==53 and rig_evidence["finger_joint_count"]==30,
        "finger_skin_green":skin_evidence["validation"]["status"]=="pass" and skin_evidence["minimum_vertices_per_segment"]>=3,
        "v0_4_open_pose_reproduced":open_vs_v4<1e-8,
        "weapon_transform_preserved":v4["weapon"]["scale"]==[1.0,1.0,1.0],
        "primary_contact_preserved":float(v4["contact"]["primary_position_error"])<1e-8,
        "support_contact_preserved":float(v4["contact"]["support_position_error"])<1e-6,
        "right_nonthumb_tips_closer":choices["right"]["curled_nonthumb_mean_m"]<choices["right"]["open_nonthumb_mean_m"],
        "left_nonthumb_tips_closer":choices["left"]["curled_nonthumb_mean_m"]<choices["left"]["open_nonthumb_mean_m"],
        "right_thumb_closer":choices["right"]["curled_thumb_m"]<choices["right"]["open_thumb_m"],
        "left_thumb_closer":choices["left"]["curled_thumb_m"]<choices["left"]["open_thumb_m"],
        "finger_surface_moves":curl_moved>200 and finger_curl_max>0.003,
        "nonfinger_rows_stationary_under_curl":nonfinger_curl_max<1e-8,
        "head_unchanged_by_curl":head_curl<1e-9,
        "lower_body_unchanged_by_curl":lower_curl<1e-9,
        "curl_bounded":finger_curl_max<0.12,
        "posed_skeleton_valid":posed_report["status"]=="pass",
    }
    result=copy.deepcopy(v4)
    result["schema"]=SCHEMA
    result["pose_id"]="cross_chest_low_ready_finger_grip_v0.5"
    result["shared_rig"]={
        "schema":rig_evidence["schema"],
        "joint_count":len(bind.joints),
        "finger_joint_count":rig_evidence["finger_joint_count"],
        "finger_indices":finger_indices,
        "finger_rig_evidence":rig_evidence,
        "finger_skin_evidence":skin_evidence,
    }
    result["finger_grip"]={
        "changed_variable_from_v0_4":"finger_joint_rotations_only_on_source_grounded_53_joint_skin",
        "selection_rule":"bounded curl sign/scale candidates minimize fingertip distance to the already-proven hand socket; Godot remains the visual promotion gate",
        "choices":choices,
        "finger_surface":finger_surface,
        "open_pose_vs_v0_4_max_error_m":open_vs_v4,
        "curl_moved_finger_vertices":curl_moved,
        "finger_curl_max_displacement_m":finger_curl_max,
        "nonfinger_curl_max_displacement_m":nonfinger_curl_max,
        "head_curl_max_displacement_m":head_curl,
        "lower_body_curl_max_displacement_m":lower_curl,
    }
    result["acceptance"]=acceptance
    result["truth"]={
        "uses_shared_full_body_rig":True,
        "source_grounded_finger_chains":True,
        "v0_4_arm_pose_preserved":True,
        "human_scale_rifle_preserved":True,
        "finger_grip_proposal":True,
        "production_grip_claim":False,
        "production_finger_skinning_claim":False,
        "automatic_visual_promotion":False,
        "notes":[
            "v0.5 changes only appended finger-joint rotations after reproducing the v0.4 arm/rifle pose on the 53-joint skin.",
            "Curl direction and bounded scale are selected deterministically from a tiny candidate set using fingertip-to-existing-socket distance, not aesthetic scoring.",
            "A closer fingertip metric is necessary but insufficient. Real Godot front, three-quarter and hand-close views decide whether the fingers actually wrap the weapon convincingly.",
            "Metacarpal articulation and compressed-knuckle correctives remain later hand-quality gates."
        ],
    }
    if not all(acceptance.values()):raise ValueError(f"v0.5 finger grip acceptance failed: {acceptance} choices={choices}")
    return posed_mesh,result


def build_preferred_finger_grip_rifle_contact_pose():
    body,_uv,_state=_load_identity_body()
    return build_finger_grip_rifle_contact_pose(body)


if __name__=="__main__":
    import json
    mesh,packet=build_preferred_finger_grip_rifle_contact_pose()
    print(json.dumps({"vertices":len(mesh.vertices),"faces":len(mesh.faces),"acceptance":packet["acceptance"],"finger_grip":packet["finger_grip"],"weapon":packet["weapon"]},indent=2))
