#!/usr/bin/env python3
"""Source-grounded finger closure over the v0.4 rifle-contact pose.

The exact v0.4 human-scale rifle, shoulder/elbow/wrist rotations and palm socket
contact are held fixed. This layer extends the shared rig with the pinned hm08
finger chains and searches a very small deterministic curl grid per hand. The
objective is physical: bring source-grounded fingertips toward the appropriate
weapon grip axis/radius while preserving palm contact and every non-finger
surface vertex from v0.4.

This is a first articulated grip, not final finger collision or trigger logic.
"""
from __future__ import annotations

import copy
from dataclasses import replace
from math import acos, cos, radians, sin, sqrt

from native_attachment import TwoHandSocketAttachment, socket_contact_evidence
from native_geometry import Mesh, Vec3
from native_hm08_finger_rig import (
    _finger_rows,
    _source_side_mapping,
    build_hm08_finger_skeleton,
    build_hm08_finger_skin_weights,
    load_finger_landmarks,
)
from native_hm08_humanoid_rig import build_hm08_humanoid_skeleton, derive_hm08_rig_landmarks
from native_hm08_rifle_contact_pose import _distance, _quat_conjugate, _quat_mul, _quat_rotate
from native_hm08_rifle_contact_pose_v2 import derive_shared_rig_arms
from native_hm08_rifle_contact_pose_v4 import build_segment_skin_rifle_contact_pose
from native_hm08_undersuit import _load_identity_body
from native_skin import Joint, Quat, Skeleton, global_joint_matrices, inverse4, skin_vertices, transform_point, validate_skeleton
from native_weapon_human_scale import sentinel_rifle_human_scale

SCHEMA = "axm.game-assets.hm08-finger-grip-pose.v0.1"


def _sub(a: Vec3,b: Vec3)->Vec3:
    return a[0]-b[0],a[1]-b[1],a[2]-b[2]


def _add(a: Vec3,b: Vec3)->Vec3:
    return a[0]+b[0],a[1]+b[1],a[2]+b[2]


def _mul(a: Vec3,s: float)->Vec3:
    return a[0]*s,a[1]*s,a[2]*s


def _dot(a: Vec3,b: Vec3)->float:
    return a[0]*b[0]+a[1]*b[1]+a[2]*b[2]


def _cross(a: Vec3,b: Vec3)->Vec3:
    return (a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0])


def _length(a: Vec3)->float:
    return sqrt(_dot(a,a))


def _normalize(a: Vec3)->Vec3:
    length=_length(a)
    if length<=1e-12:raise ValueError("cannot normalize zero vector")
    return a[0]/length,a[1]/length,a[2]/length


def _axis_angle(axis: Vec3, degrees: float)->Quat:
    axis=_normalize(axis)
    half=radians(degrees)*0.5
    s=sin(half)
    return axis[0]*s,axis[1]*s,axis[2]*s,cos(half)


def _from_to_limited(source: Vec3,target: Vec3,max_degrees: float)->Quat:
    a=_normalize(source);b=_normalize(target)
    dot=max(-1.0,min(1.0,_dot(a,b)))
    angle=acos(dot)
    if angle<=1e-9:return (0.0,0.0,0.0,1.0)
    axis=_cross(a,b)
    if _length(axis)<=1e-9:return (0.0,0.0,0.0,1.0)
    return _axis_angle(axis,min(max_degrees,angle*180.0/3.141592653589793))


def _distance_to_axis(point: Vec3,center: Vec3,axis: Vec3)->tuple[float,float]:
    axis=_normalize(axis)
    delta=_sub(point,center)
    along=_dot(delta,axis)
    radial=_sub(delta,_mul(axis,along))
    return _length(radial),along


def _apply_arm_pose(base: Skeleton, base_indices: dict[str,int], v4: dict[str,object])->Skeleton:
    joints=list(base.joints)
    for side in ("right","left"):
        row=v4["pose"][side]
        for key,rotation_key in (("upper_arm","shoulder_rotation"),("forearm","elbow_rotation"),("hand","hand_rotation")):
            index=base_indices[f"{side}_{key}"]
            source=joints[index]
            rotation=tuple(float(value) for value in row[rotation_key])
            joints[index]=Joint(source.name,source.parent,source.translation,rotation,source.scale)
    posed=Skeleton(joints)
    report=validate_skeleton(posed)
    if report["status"]!="pass":raise ValueError(f"arm pose reconstruction failed: {report}")
    return posed


def _source_flex_axes(packet: dict[str,object], mapping: dict[str,str], rows: dict[tuple[str,int,int],dict[str,object]])->dict[str,dict[str,Vec3]]:
    result={}
    for side in ("left","right"):
        index_root=tuple(float(v) for v in rows[(side,2,1)]["head_m"])
        pinky_root=tuple(float(v) for v in rows[(side,5,1)]["head_m"])
        middle_head=tuple(float(v) for v in rows[(side,3,1)]["head_m"])
        middle_tail=tuple(float(v) for v in rows[(side,3,1)]["tail_m"])
        spread=_normalize(_sub(pinky_root,index_root))
        finger_direction=_normalize(_sub(middle_tail,middle_head))
        palm_normal=_normalize(_cross(finger_direction,spread))
        result[side]={"flex_axis":spread,"palm_normal":palm_normal,"finger_direction":finger_direction}
    return result


def _finger_tip_world(skeleton: Skeleton,finger_indices:dict[str,int],rig_evidence:dict[str,object],side:str,digit:int)->Vec3:
    index=finger_indices[f"{side}_finger{digit}_3"]
    offset=tuple(float(v) for v in rig_evidence["tip_local_offsets"][f"{side}_finger{digit}_tip"])
    return transform_point(global_joint_matrices(skeleton)[index],offset)


def _curl_fingers(
    arm_posed: Skeleton,
    finger_indices: dict[str,int],
    rig_evidence: dict[str,object],
    axes: dict[str,dict[str,Vec3]],
    side: str,
    sign: float,
    multiplier: float,
    grip_center: Vec3,
    grip_axis_world: Vec3,
    grip_radius: float,
)->tuple[Skeleton,dict[str,object]]:
    joints=list(arm_posed.joints)
    digit_multiplier={2:0.94,3:1.00,4:1.05,5:1.10}
    base_angles={1:52.0,2:72.0,3:54.0}
    flex_axis=axes[side]["flex_axis"]
    for digit in range(2,6):
        factor=digit_multiplier[digit]*multiplier
        for segment in range(1,4):
            index=finger_indices[f"{side}_finger{digit}_{segment}"]
            source=joints[index]
            curl=_axis_angle(flex_axis,sign*base_angles[segment]*factor)
            joints[index]=replace(source,rotation=curl)

    candidate=Skeleton(joints)
    report=validate_skeleton(candidate)
    if report["status"]!="pass":raise ValueError(report)
    tips={digit:_finger_tip_world(candidate,finger_indices,rig_evidence,side,digit) for digit in range(2,6)}
    radial={}
    objective=0.0
    for digit,tip in tips.items():
        distance,along=_distance_to_axis(tip,grip_center,grip_axis_world)
        radial[digit]={"distance_m":distance,"axis_offset_m":along,"radius_error_m":abs(distance-grip_radius)}
        objective+=abs(distance-grip_radius)+max(0.0,abs(along)-0.11)*0.35
    return candidate,{"sign":sign,"multiplier":multiplier,"objective":objective,"tips":{str(k):list(v) for k,v in tips.items()},"radial":{str(k):v for k,v in radial.items()}}


def _add_thumb_opposition(
    skeleton: Skeleton,
    finger_indices: dict[str,int],
    rig_evidence: dict[str,object],
    rows: dict[tuple[str,int,int],dict[str,object]],
    axes: dict[str,dict[str,Vec3]],
    side: str,
    sign: float,
    grip_center: Vec3,
)->tuple[Skeleton,dict[str,object]]:
    joints=list(skeleton.joints)
    root=tuple(float(v) for v in rows[(side,1,1)]["head_m"])
    bind_direction=_sub(tuple(float(v) for v in rows[(side,1,1)]["tail_m"]),root)
    hand_index=next(index for index,joint in enumerate(joints) if joint.name==f"{side}_hand")
    hand_world=global_joint_matrices(skeleton)[hand_index]
    grip_local=transform_point(inverse4(hand_world),grip_center)
    desired=_sub(grip_local,root)
    opposition=_from_to_limited(bind_direction,desired,34.0)
    flex_axis=axes[side]["flex_axis"]
    thumb_angles={1:14.0,2:38.0,3:34.0}
    for segment in range(1,4):
        index=finger_indices[f"{side}_finger1_{segment}"]
        source=joints[index]
        curl=_axis_angle(flex_axis,sign*thumb_angles[segment])
        rotation=_quat_mul(opposition,curl) if segment==1 else curl
        joints[index]=replace(source,rotation=rotation)
    posed=Skeleton(joints)
    report=validate_skeleton(posed)
    if report["status"]!="pass":raise ValueError(report)
    tip=_finger_tip_world(posed,finger_indices,rig_evidence,side,1)
    return posed,{"opposition_limit_deg":34.0,"curl_angles_deg":thumb_angles,"tip_world":list(tip),"tip_to_grip_center_m":_distance(tip,grip_center)}


def build_hm08_finger_grip_pose(body: Mesh)->tuple[Mesh,dict[str,object]]:
    v4_mesh,v4=build_segment_skin_rifle_contact_pose(body)
    packet=load_finger_landmarks()
    mapping=_source_side_mapping(packet)
    rows=_finger_rows(packet,mapping)
    finger_skeleton,finger_indices,rig_evidence=build_hm08_finger_skeleton(body)
    finger_weights,skin_evidence=build_hm08_finger_skin_weights(body,finger_skeleton,finger_indices)
    _base,_base_evidence,base_indices=build_hm08_humanoid_skeleton(body)
    arm_posed=_apply_arm_pose(finger_skeleton,base_indices,v4)
    axes=_source_flex_axes(packet,mapping,rows)
    rifle=sentinel_rifle_human_scale()
    weapon_rotation=tuple(float(v) for v in v4["weapon"]["rotation"])
    primary_center=tuple(float(v) for v in v4["contact"]["primary_hand_contact_world_position"])
    support_center=tuple(float(v) for v in v4["contact"]["support_hand_contact_world_position"])
    grip_state={
        "right":{"center":primary_center,"axis":_quat_rotate(weapon_rotation,(0.0,1.0,0.0)),"radius":0.033},
        "left":{"center":support_center,"axis":_quat_rotate(weapon_rotation,(1.0,0.0,0.0)),"radius":0.044},
    }

    current=arm_posed
    search_evidence={}
    for side in ("right","left"):
        candidates=[]
        for sign in (-1.0,1.0):
            for multiplier in (0.70,0.85,1.00,1.15):
                candidate,row=_curl_fingers(current,finger_indices,rig_evidence,axes,side,sign,multiplier,grip_state[side]["center"],grip_state[side]["axis"],grip_state[side]["radius"])
                candidates.append((float(row["objective"]),sign,multiplier,candidate,row))
        candidates.sort(key=lambda item:(item[0],item[1],item[2]))
        _objective,sign,multiplier,current,best=candidates[0]
        current,thumb=_add_thumb_opposition(current,finger_indices,rig_evidence,rows,axes,side,sign,grip_state[side]["center"])
        search_evidence[side]={"selected":best,"thumb":thumb,"candidate_objectives":[{"sign":item[1],"multiplier":item[2],"objective":item[0]} for item in candidates]}

    # Contact is re-measured with explicit character palm sockets after all
    # finger rotations. Finger joints are descendants and must not move palms.
    landmarks=derive_hm08_rig_landmarks(body)
    arms=derive_shared_rig_arms(body,landmarks)
    attachment=TwoHandSocketAttachment(
        primary_joint=base_indices["right_hand"],support_joint=base_indices["left_hand"],
        primary_hand_socket=arms["right"].hand_socket,support_hand_socket=arms["left"].hand_socket,
        primary_weapon_socket=rifle.sockets["primary_grip"],support_weapon_socket=rifle.sockets["support_grip"],
    )
    contact=socket_contact_evidence(current,attachment)
    posed_vertices=skin_vertices(body,finger_weights,finger_skeleton,current)
    posed_mesh=Mesh("sentinel_hm08_articulated_grip_v0_1",posed_vertices,list(body.faces))

    finger_joint_set=set(finger_indices.values())
    nonfinger_max=0.0
    finger_changed=0
    for index,(before,after) in enumerate(zip(v4_mesh.vertices,posed_mesh.vertices)):
        has_finger=any(joint in finger_joint_set and weight>1e-9 for joint,weight in zip(finger_weights.joints[index],finger_weights.weights[index]))
        distance=_distance(before,after)
        if has_finger:
            if distance>1e-8:finger_changed+=1
        else:
            nonfinger_max=max(nonfinger_max,distance)

    final_tips={}
    for side in ("right","left"):
        final_tips[side]={}
        for digit in range(1,6):
            tip=_finger_tip_world(current,finger_indices,rig_evidence,side,digit)
            radial,along=_distance_to_axis(tip,grip_state[side]["center"],grip_state[side]["axis"])
            final_tips[side][str(digit)]={"position":list(tip),"radial_distance_m":radial,"axis_offset_m":along,"target_radius_m":grip_state[side]["radius"],"radius_error_m":abs(radial-grip_state[side]["radius"])}

    evidence={
        "schema":SCHEMA,
        "pose_id":"source_grounded_rifle_grip_v0.1",
        "changed_variable_from_v0_4":"finger_skeleton_weights_and_grip_closure_only",
        "finger_rig":rig_evidence,
        "finger_skin":skin_evidence,
        "grip_state":{side:{"center":list(row["center"]),"axis":list(row["axis"]),"radius_m":row["radius"]} for side,row in grip_state.items()},
        "curl_search":search_evidence,
        "final_fingertips":final_tips,
        "contact":contact,
        "weapon":copy.deepcopy(v4["weapon"]),
        "arm_pose":copy.deepcopy(v4["pose"]),
        "finger_changed_vertices":finger_changed,
        "nonfinger_max_delta_from_v0_4_m":nonfinger_max,
        "truth":{
            "v0_4_arm_pose_preserved":True,
            "human_scale_rifle_preserved":True,
            "palm_socket_contact_preserved":True,
            "source_grounded_finger_pivots":True,
            "finger_collision_solver_claim":False,
            "trigger_finger_claim":False,
            "production_grip_claim":False,
            "automatic_visual_promotion":False,
            "notes":[
                "The four non-thumb digits choose only sign and a small curl multiplier grid against deterministic grip-axis/radius error; no screenshot fitting or hidden optimization is used.",
                "Thumb opposition is bounded toward the same grip center using the pinned source thumb direction and an explicit 34-degree cap.",
                "Palm sockets, arm pose and weapon state are inherited unchanged from v0.4, so the next Godot A/B isolates articulated finger closure."
            ],
        },
    }
    return posed_mesh,evidence


def build_preferred_hm08_finger_grip_pose():
    body,_uv,_state=_load_identity_body()
    return build_hm08_finger_grip_pose(body)


if __name__=="__main__":
    import json
    mesh,evidence=build_preferred_hm08_finger_grip_pose()
    print(json.dumps({"vertices":len(mesh.vertices),"faces":len(mesh.faces),**evidence},indent=2))
