#!/usr/bin/env python3
"""Rifle contact v0.5: preserve v0.4 and close source-grounded finger chains.

Run 2 proved the human-scale rifle, two-hand socket contact, shared arm pose and
bone-segment arm skin. The merged Forge also contains a 53-joint skeleton with
30 source-grounded finger pivots plus finger-local skin weights.

This layer changes only finger-joint rotations. Each digit is solved in its
actual parent coordinate frame toward the already-proven weapon grip socket.
Rotations are angle-capped and selected from a tiny deterministic scale set.
That geometric objective is only a proposal gate: real Godot hand close-ups
remain the visual promotion boundary.
"""
from __future__ import annotations

import copy
from dataclasses import replace
from math import acos, cos, degrees, radians, sin, sqrt

from native_geometry import Mesh, bounds
from native_hm08_finger_rig import (
    build_hm08_finger_skeleton,
    build_hm08_finger_skin_weights,
)
from native_hm08_rifle_contact_pose import _centroid, _distance, _quat_from_to, _quat_mul
from native_hm08_rifle_contact_pose_v4 import build_segment_skin_rifle_contact_pose
from native_hm08_undersuit import _load_identity_body
from native_skin import (
    Joint,
    Quat,
    Skeleton,
    global_joint_matrices,
    inverse4,
    normalize_quaternion,
    skin_vertices,
    transform_point,
    validate_skeleton,
)

SCHEMA = "axm.game-assets.hm08-rifle-contact-pose.v0.5"
SCALE_CANDIDATES = (0.18, 0.32, 0.50, 0.70, 0.90, 1.00)
NONTHUMB_CAP_DEG = {1: 50.0, 2: 70.0, 3: 60.0}
THUMB_CAP_DEG = {1: 35.0, 2: 50.0, 3: 40.0}


def _sub(a, b):
    return a[0]-b[0], a[1]-b[1], a[2]-b[2]


def _dot(a, b) -> float:
    return a[0]*b[0]+a[1]*b[1]+a[2]*b[2]


def _length(a) -> float:
    return sqrt(_dot(a,a))


def _normalize(a):
    length=_length(a)
    if length<=1e-12:
        raise ValueError("cannot normalize zero grip vector")
    return a[0]/length,a[1]/length,a[2]/length


def _axis_angle(axis, angle_rad: float) -> Quat:
    axis=_normalize(axis)
    half=angle_rad*0.5
    s=sin(half)
    return normalize_quaternion((axis[0]*s,axis[1]*s,axis[2]*s,cos(half)))


def _scaled_capped_from_to(source, target, max_degrees: float):
    """Shortest from-to rotation, capped without changing its axis."""
    q=_quat_from_to(source,target)
    q=normalize_quaternion(q)
    w=max(-1.0,min(1.0,q[3]))
    angle=2.0*acos(w)
    if angle<=1e-10:
        return (0.0,0.0,0.0,1.0),0.0,0.0,(0.0,0.0,1.0)
    sin_half=sin(angle*0.5)
    if abs(sin_half)<=1e-10:
        axis=(q[0],q[1],q[2])
    else:
        axis=(q[0]/sin_half,q[1]/sin_half,q[2]/sin_half)
    axis=_normalize(axis)
    capped=min(angle,radians(max_degrees))
    return _axis_angle(axis,capped),degrees(angle),degrees(capped),axis


def _tip_world(skeleton: Skeleton, indices: dict[str,int], rig_evidence: dict[str,object], side: str, digit: int):
    matrices=global_joint_matrices(skeleton)
    joint=indices[f"{side}_finger{digit}_3"]
    offset=tuple(float(v) for v in rig_evidence["tip_local_offsets"][f"{side}_finger{digit}_tip"])
    return transform_point(matrices[joint],offset)


def _digit_source_vector(bind: Skeleton, indices: dict[str,int], rig_evidence: dict[str,object], side: str, digit: int, segment: int):
    if segment<3:
        child=indices[f"{side}_finger{digit}_{segment+1}"]
        return bind.joints[child].translation
    return tuple(float(v) for v in rig_evidence["tip_local_offsets"][f"{side}_finger{digit}_tip"])


def _solve_digit(
    base: Skeleton,
    bind: Skeleton,
    indices: dict[str,int],
    rig_evidence: dict[str,object],
    side: str,
    digit: int,
    socket_world,
    scale: float,
):
    joints=list(base.joints)
    caps=THUMB_CAP_DEG if digit==1 else NONTHUMB_CAP_DEG
    rows=[]
    for segment in range(1,4):
        current=Skeleton(joints)
        matrices=global_joint_matrices(current)
        joint_index=indices[f"{side}_finger{digit}_{segment}"]
        joint=joints[joint_index]
        if joint.parent is None:
            raise ValueError("finger joint unexpectedly has no parent")
        socket_parent=transform_point(inverse4(matrices[joint.parent]),socket_world)
        target_direction=_sub(socket_parent,joint.translation)
        source_direction=_digit_source_vector(bind,indices,rig_evidence,side,digit,segment)
        q,full_angle,applied_angle,axis=_scaled_capped_from_to(
            source_direction,target_direction,caps[segment]*scale
        )
        joints[joint_index]=replace(joint,rotation=_quat_mul(joint.rotation,q))
        rows.append({
            "segment":segment,
            "full_target_angle_deg":full_angle,
            "applied_angle_deg":applied_angle,
            "cap_deg":caps[segment]*scale,
            "axis_parent_space":list(axis),
        })
    solved=Skeleton(joints)
    validation=validate_skeleton(solved)
    if validation["status"]!="pass":
        raise ValueError(f"digit solve produced invalid skeleton: {validation}")
    return solved,rows


def _reconstruct_v4_on_finger_rig(body_m: Mesh):
    v4_mesh,v4=build_segment_skin_rifle_contact_pose(body_m)
    bind,finger_indices,rig_evidence=build_hm08_finger_skeleton(body_m)
    weights,skin_evidence=build_hm08_finger_skin_weights(body_m,bind,finger_indices)
    indices={joint.name:index for index,joint in enumerate(bind.joints)}
    joints=list(bind.joints)
    for side in ("right","left"):
        row=v4["pose"][side]
        for suffix,key in (
            ("upper_arm","shoulder_rotation"),
            ("forearm","elbow_rotation"),
            ("hand","hand_rotation"),
        ):
            index=indices[f"{side}_{suffix}"]
            source=joints[index]
            joints[index]=replace(source,rotation=tuple(float(v) for v in row[key]))
    open_skeleton=Skeleton(joints)
    validation=validate_skeleton(open_skeleton)
    if validation["status"]!="pass":
        raise ValueError(f"extended v0.4 reconstruction invalid: {validation}")
    open_mesh=Mesh(
        "sentinel_hm08_finger_rig_open_contact_v0_5",
        skin_vertices(body_m,weights,bind,open_skeleton),
        list(body_m.faces),
    )
    return v4_mesh,v4,bind,weights,indices,rig_evidence,skin_evidence,open_skeleton,open_mesh


def build_finger_grip_rifle_contact_pose(body_m: Mesh) -> tuple[Mesh,dict[str,object]]:
    (
        v4_mesh,v4,bind,weights,indices,rig_evidence,skin_evidence,open_skeleton,open_mesh
    )=_reconstruct_v4_on_finger_rig(body_m)

    finger_joint_set=set(rig_evidence["finger_indices"].values())
    open_vs_v4_all=0.0
    open_vs_v4_finger=0.0
    open_vs_v4_nonfinger=0.0
    for vertex_index,(a,b) in enumerate(zip(open_mesh.vertices,v4_mesh.vertices)):
        error=_distance(a,b)
        open_vs_v4_all=max(open_vs_v4_all,error)
        active=any(
            joint in finger_joint_set and weight>1e-9
            for joint,weight in zip(weights.joints[vertex_index],weights.weights[vertex_index])
        )
        if active:open_vs_v4_finger=max(open_vs_v4_finger,error)
        else:open_vs_v4_nonfinger=max(open_vs_v4_nonfinger,error)

    sockets={
        "right":tuple(float(v) for v in v4["contact"]["primary_hand_contact_world_position"]),
        "left":tuple(float(v) for v in v4["contact"]["support_hand_contact_world_position"]),
    }
    current=open_skeleton
    choices={}
    all_improvements=[]
    for side in ("right","left"):
        side_rows={"socket_world":list(sockets[side]),"digits":{}}
        for digit in range(1,6):
            open_tip=_tip_world(current,indices,rig_evidence,side,digit)
            open_distance=_distance(open_tip,sockets[side])
            candidates=[]
            for scale in SCALE_CANDIDATES:
                candidate,segments=_solve_digit(
                    current,bind,indices,rig_evidence,side,digit,sockets[side],scale
                )
                tip=_tip_world(candidate,indices,rig_evidence,side,digit)
                distance=_distance(tip,sockets[side])
                candidates.append((distance,scale,candidate,tip,segments))
            candidates.sort(key=lambda row:(row[0],row[1]))
            distance,scale,current,tip,segments=candidates[0]
            improvement=open_distance-distance
            all_improvements.append(improvement)
            side_rows["digits"][str(digit)]={
                "scale":scale,
                "open_tip_world":list(open_tip),
                "curled_tip_world":list(tip),
                "open_tip_to_socket_m":open_distance,
                "curled_tip_to_socket_m":distance,
                "improvement_m":improvement,
                "segments":segments,
            }
        open_values=[row["open_tip_to_socket_m"] for row in side_rows["digits"].values()]
        curled_values=[row["curled_tip_to_socket_m"] for row in side_rows["digits"].values()]
        side_rows["open_tip_mean_m"]=sum(open_values)/len(open_values)
        side_rows["curled_tip_mean_m"]=sum(curled_values)/len(curled_values)
        side_rows["mean_improvement_m"]=side_rows["open_tip_mean_m"]-side_rows["curled_tip_mean_m"]
        choices[side]=side_rows

    posed=current
    posed_report=validate_skeleton(posed)
    if posed_report["status"]!="pass":
        raise ValueError(f"v0.5 posed skeleton invalid: {posed_report}")
    posed_mesh=Mesh(
        "sentinel_hm08_finger_grip_rifle_contact_v0_5",
        skin_vertices(body_m,weights,bind,posed),
        list(body_m.faces),
    )

    curl_moved=0
    nonfinger_curl_max=0.0
    finger_curl_max=0.0
    finger_surface={}
    for vertex_index,(before,after) in enumerate(zip(open_mesh.vertices,posed_mesh.vertices)):
        delta=_distance(before,after)
        active=any(
            joint in finger_joint_set and weight>1e-9
            for joint,weight in zip(weights.joints[vertex_index],weights.weights[vertex_index])
        )
        if active:
            if delta>1e-10:curl_moved+=1
            finger_curl_max=max(finger_curl_max,delta)
        else:
            nonfinger_curl_max=max(nonfinger_curl_max,delta)

    for side in ("right","left"):
        side_joint_set={index for name,index in rig_evidence["finger_indices"].items() if name.startswith(side+"_")}
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
        "v0_4_nonfinger_pose_reproduced":open_vs_v4_nonfinger<1e-9,
        "v0_4_open_pose_reproduced_within_micron":open_vs_v4_all<1e-6,
        "weapon_transform_preserved":v4["weapon"]["scale"]==[1.0,1.0,1.0],
        "primary_contact_preserved":float(v4["contact"]["primary_position_error"])<1e-8,
        "support_contact_preserved":float(v4["contact"]["support_position_error"])<1e-6,
        "every_fingertip_closer":len(all_improvements)==10 and min(all_improvements)>1e-6,
        "both_hand_means_closer":all(choices[side]["curled_tip_mean_m"]<choices[side]["open_tip_mean_m"] for side in ("right","left")),
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
        "finger_indices":rig_evidence["finger_indices"],
        "finger_rig_evidence":rig_evidence,
        "finger_skin_evidence":skin_evidence,
    }
    result["finger_grip"]={
        "changed_variable_from_v0_4":"finger_joint_rotations_only_on_source_grounded_53_joint_skin",
        "selection_rule":"per-digit parent-space shortest rotation toward the existing weapon socket, bounded by phalanx angle caps and a small deterministic scale set; Godot remains the visual promotion gate",
        "scale_candidates":list(SCALE_CANDIDATES),
        "choices":choices,
        "finger_surface":finger_surface,
        "open_pose_vs_v0_4_max_error_m":open_vs_v4_all,
        "open_pose_vs_v0_4_finger_max_error_m":open_vs_v4_finger,
        "open_pose_vs_v0_4_nonfinger_max_error_m":open_vs_v4_nonfinger,
        "minimum_fingertip_improvement_m":min(all_improvements),
        "mean_fingertip_improvement_m":sum(all_improvements)/len(all_improvements),
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
            "v0.5 changes only appended finger-joint rotations after reproducing v0.4 on the 53-joint skin.",
            "Each digit solves in its current parent coordinate frame toward the already-proven hand socket. Rotation is shortest-path and angle-capped per phalanx.",
            "A closer fingertip metric is necessary but insufficient. Real Godot front, three-quarter and hand-close views decide whether the fingers actually wrap the weapon convincingly.",
            "Metacarpal articulation, grip-volume collision and compressed-knuckle correctives remain later hand-quality gates."
        ],
    }
    if not all(acceptance.values()):
        raise ValueError(
            f"v0.5 finger grip acceptance failed: {acceptance}; "
            f"open_vs_v4_all={open_vs_v4_all:.9g} finger={open_vs_v4_finger:.9g} nonfinger={open_vs_v4_nonfinger:.9g}; "
            f"min_tip_improvement={min(all_improvements):.9g}; choices={choices}"
        )
    return posed_mesh,result


def build_preferred_finger_grip_rifle_contact_pose():
    body,_uv,_state=_load_identity_body()
    return build_finger_grip_rifle_contact_pose(body)


if __name__=="__main__":
    import json
    mesh,packet=build_preferred_finger_grip_rifle_contact_pose()
    print(json.dumps({
        "vertices":len(mesh.vertices),
        "faces":len(mesh.faces),
        "acceptance":packet["acceptance"],
        "finger_grip":packet["finger_grip"],
        "weapon":packet["weapon"],
    },indent=2))
