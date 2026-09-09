#!/usr/bin/env python3
"""Rifle contact v0.5: preserve v0.4 arm/contact state and close fingers.

The merged Forge already has a source-grounded 53-joint rig and finger-local
skin. Those finger weights intentionally differ from v0.4's rigid-hand weights,
so a byte-identical v0.4 posed mesh is not the right invariant. This layer
preserves the proven v0.4 arm rotations, rifle transform and socket contact,
then changes only appended finger-joint rotations.

Each digit solves in its actual parent coordinate frame toward the existing
weapon socket. Rotations are shortest-path, angle-capped, and selected from a
small deterministic scale set. Real Godot hand close-ups remain the promotion
gate; geometric closeness alone is never aesthetic approval.
"""
from __future__ import annotations

import copy
from dataclasses import replace
from math import acos, cos, degrees, radians, sin, sqrt

from native_geometry import Mesh, bounds
from native_hm08_finger_rig import build_hm08_finger_skeleton, build_hm08_finger_skin_weights
from native_hm08_rifle_contact_pose import _centroid, _distance, _quat_from_to, _quat_mul
from native_hm08_rifle_contact_pose_v4 import build_segment_skin_rifle_contact_pose
from native_hm08_undersuit import _load_identity_body
from native_skin import (
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
    q=normalize_quaternion(_quat_from_to(source,target))
    w=max(-1.0,min(1.0,q[3]))
    angle=2.0*acos(w)
    if angle<=1e-10:
        return (0.0,0.0,0.0,1.0),0.0,0.0,(0.0,0.0,1.0)
    sin_half=sin(angle*0.5)
    axis=(q[0],q[1],q[2]) if abs(sin_half)<=1e-10 else (q[0]/sin_half,q[1]/sin_half,q[2]/sin_half)
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


def _solve_digit(base: Skeleton, bind: Skeleton, indices: dict[str,int], rig_evidence: dict[str,object], side: str, digit: int, socket_world, scale: float):
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
        q,full_angle,applied_angle,axis=_scaled_capped_from_to(source_direction,target_direction,caps[segment]*scale)
        joints[joint_index]=replace(joint,rotation=_quat_mul(joint.rotation,q))
        rows.append({
            "segment":segment,
            "full_target_angle_deg":full_angle,
            "applied_angle_deg":applied_angle,
            "cap_deg":caps[segment]*scale,
            "axis_parent_space":list(axis),
        })
    solved=Skeleton(joints)
    report=validate_skeleton(solved)
    if report["status"]!="pass":
        raise ValueError(f"digit solve produced invalid skeleton: {report}")
    return solved,rows


def _reconstruct_v4_on_finger_rig(body_m: Mesh):
    v4_mesh,v4=build_segment_skin_rifle_contact_pose(body_m)
    bind,finger_indices,rig_evidence=build_hm08_finger_skeleton(body_m)
    weights,skin_evidence=build_hm08_finger_skin_weights(body_m,bind,finger_indices)
    indices={joint.name:index for index,joint in enumerate(bind.joints)}
    joints=list(bind.joints)
    for side in ("right","left"):
        row=v4["pose"][side]
        for suffix,key in (("upper_arm","shoulder_rotation"),("forearm","elbow_rotation"),("hand","hand_rotation")):
            index=indices[f"{side}_{suffix}"]
            joints[index]=replace(joints[index],rotation=tuple(float(v) for v in row[key]))
    open_skeleton=Skeleton(joints)
    report=validate_skeleton(open_skeleton)
    if report["status"]!="pass":
        raise ValueError(f"extended v0.4 reconstruction invalid: {report}")
    open_mesh=Mesh(
        "sentinel_hm08_finger_skin_open_contact_v0_5",
        skin_vertices(body_m,weights,bind,open_skeleton),
        list(body_m.faces),
    )
    arm_rotation_exact=True
    for side in ("right","left"):
        row=v4["pose"][side]
        for suffix,key in (("upper_arm","shoulder_rotation"),("forearm","elbow_rotation"),("hand","hand_rotation")):
            expected=tuple(float(v) for v in row[key])
            arm_rotation_exact=arm_rotation_exact and open_skeleton.joints[indices[f"{side}_{suffix}"]].rotation==expected
    return v4_mesh,v4,bind,weights,indices,rig_evidence,skin_evidence,open_skeleton,open_mesh,arm_rotation_exact


def build_finger_grip_rifle_contact_pose(body_m: Mesh) -> tuple[Mesh,dict[str,object]]:
    (
        v4_mesh,v4,bind,weights,indices,rig_evidence,skin_evidence,open_skeleton,open_mesh,arm_rotation_exact
    )=_reconstruct_v4_on_finger_rig(body_m)

    # Run 2's merged finger skin deliberately reweights a bounded hand/finger
    # neighborhood relative to v0.4. Record that visual baseline delta, but do
    # not misclassify it as arm-pose drift.
    open_vs_v4=max(_distance(a,b) for a,b in zip(open_mesh.vertices,v4_mesh.vertices))

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
                candidate,segments=_solve_digit(current,bind,indices,rig_evidence,side,digit,sockets[side],scale)
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

    finger_joint_set=set(rig_evidence["finger_indices"].values())
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

    finger_surface={}
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

    skin_preserved=(
        skin_evidence["preserved_nonfinger_rows"]==skin_evidence["expected_preserved_nonfinger_rows"]
        and skin_evidence["truth"]["shared_body_skin_preserved_outside_fingers"] is True
    )
    acceptance={
        "finger_rig_53_joints":len(bind.joints)==53 and rig_evidence["finger_joint_count"]==30,
        "finger_skin_green":skin_evidence["validation"]["status"]=="pass" and skin_evidence["minimum_vertices_per_segment"]>=3,
        "finger_skin_preserves_nonfinger_v2_rows":skin_preserved,
        "v0_4_arm_joint_rotations_preserved":arm_rotation_exact,
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
        "changed_variable_from_merged_finger_skin_open_pose":"finger_joint_rotations_only",
        "v0_4_arm_and_weapon_reference":{
            "arm_joint_rotations_preserved":arm_rotation_exact,
            "weapon_scale":v4["weapon"]["scale"],
            "primary_position_error_m":v4["contact"]["primary_position_error"],
            "support_position_error_m":v4["contact"]["support_position_error"],
        },
        "open_53_joint_finger_skin_vs_v0_4_max_mesh_delta_m":open_vs_v4,
        "open_baseline_interpretation":"Expected difference from v0.4: the merged finger-skin layer intentionally reweights the bounded hand/finger neighborhood while preserving every row outside that neighborhood from humanoid skin v0.2.",
        "selection_rule":"per-digit parent-space shortest rotation toward the existing weapon socket, bounded by phalanx angle caps and a small deterministic scale set; Godot remains the visual promotion gate",
        "scale_candidates":list(SCALE_CANDIDATES),
        "choices":choices,
        "finger_surface":finger_surface,
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
        "v0_4_mesh_identity_claim":False,
        "human_scale_rifle_preserved":True,
        "finger_grip_proposal":True,
        "production_grip_claim":False,
        "production_finger_skinning_claim":False,
        "automatic_visual_promotion":False,
        "notes":[
            "The merged finger skin intentionally changes the hand/finger neighborhood relative to v0.4; v0.5 therefore preserves v0.4 arm rotations/contact/weapon state rather than falsely requiring mesh identity.",
            "Every humanoid-skin v0.2 row outside the finger-reweighted neighborhood remains preserved by the merged finger skin.",
            "Each digit solves in its current parent coordinate frame toward the existing hand socket with capped shortest-path rotations.",
            "A closer fingertip metric is necessary but insufficient. Real Godot front, three-quarter and hand-close views decide whether the grip actually looks convincing.",
            "Metacarpal articulation, grip-volume collision and compressed-knuckle correctives remain later hand-quality gates."
        ],
    }
    if not all(acceptance.values()):
        raise ValueError(f"v0.5 finger grip acceptance failed: {acceptance}; min_tip_improvement={min(all_improvements):.9g}; choices={choices}")
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
