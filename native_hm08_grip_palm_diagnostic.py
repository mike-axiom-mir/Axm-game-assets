#!/usr/bin/env python3
"""Diagnostic for the v0.7 physical-palm start state.

This does not promote a grip. It reconstructs v0.7 only through the re-solved
open-finger palm pose, then measures the source-grounded knuckle plane and
finger roots against the actual primary-grip / foregrip volumes. The purpose is
to distinguish insufficient palm clearance from incorrect hand orientation.
"""
from __future__ import annotations

import json
from dataclasses import replace
from math import acos, degrees, sqrt

from native_hm08_humanoid_rig import derive_hm08_rig_landmarks
from native_hm08_rifle_contact_pose import _distance, _quat_mul
from native_hm08_rifle_contact_pose_v2 import _joint_target_for_contact, _solve_arm_rotations, derive_shared_rig_arms
from native_hm08_rifle_contact_pose_v5 import _reconstruct_v4_on_finger_rig, _tip_world
from native_hm08_rifle_contact_pose_v6 import _dot, _grip_volume, _mul, _sub, _surface_gap
from native_hm08_rifle_contact_pose_v7 import _near_surface_palm_target
from native_hm08_undersuit import _load_identity_body
from native_skin import Skeleton, global_joint_matrices, transform_point, validate_skeleton
from native_weapon_human_scale import sentinel_rifle_human_scale

SCHEMA = "axm.game-assets.hm08-grip-palm-diagnostic.v0.1"


def _add(a,b):
    return a[0]+b[0],a[1]+b[1],a[2]+b[2]


def _cross(a,b):
    return (a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0])


def _length(a):
    return sqrt(_dot(a,a))


def _normalize(a):
    length=_length(a)
    if length<=1e-12:
        raise ValueError("zero palm diagnostic vector")
    return a[0]/length,a[1]/length,a[2]/length


def _mean(points):
    inv=1.0/len(points)
    return tuple(sum(point[axis] for point in points)*inv for axis in range(3))


def _angle(a,b):
    return degrees(acos(max(-1.0,min(1.0,_dot(_normalize(a),_normalize(b))))))


def build_grip_palm_diagnostic():
    body,_uv,_state=_load_identity_body()
    (
        _v4_mesh,v4,bind,_weights,indices,rig_evidence,_skin_evidence,v4_open_skeleton,_v4_open_mesh,_arm_rotation_exact
    )=_reconstruct_v4_on_finger_rig(body)
    rifle=sentinel_rifle_human_scale()
    weapon_rotation=tuple(float(value) for value in v4["weapon"]["rotation"])
    weapon_translation=tuple(float(value) for value in v4["weapon"]["translation"])
    volumes={
        "right":_grip_volume(rifle.components["primary_grip"],weapon_rotation,weapon_translation,name="primary_grip"),
        "left":_grip_volume(rifle.components["foregrip"],weapon_rotation,weapon_translation,name="foregrip"),
    }
    landmarks=derive_hm08_rig_landmarks(body)
    arms=derive_shared_rig_arms(body,landmarks)
    v4_globals=global_joint_matrices(v4_open_skeleton)
    joints=list(bind.joints)
    targets={}
    for side,sign,socket_key,contact_key in (
        ("right",1.0,"primary_grip","primary_hand_contact_world_position"),
        ("left",-1.0,"support_grip","support_hand_contact_world_position"),
    ):
        hand_index=indices[f"{side}_hand"]
        hand_joint_world=(v4_globals[hand_index][0][3],v4_globals[hand_index][1][3],v4_globals[hand_index][2][3])
        old_center=tuple(float(value) for value in v4["contact"][contact_key])
        surface_target,target_evidence=_near_surface_palm_target(volumes[side],old_center,hand_joint_world)
        desired_hand_rotation=_quat_mul(weapon_rotation,rifle.sockets[socket_key].rotation)
        joint_target=_joint_target_for_contact(surface_target,arms[side].hand_socket,desired_hand_rotation)
        elbow,shoulder_rotation,elbow_rotation,hand_rotation=_solve_arm_rotations(arms[side],joint_target,desired_hand_rotation,sign=sign)
        for suffix,rotation in (("upper_arm",shoulder_rotation),("forearm",elbow_rotation),("hand",hand_rotation)):
            index=indices[f"{side}_{suffix}"]
            joints[index]=replace(joints[index],rotation=rotation)
        targets[side]={"surface_target":surface_target,"target_evidence":target_evidence,"joint_target":joint_target}

    posed=Skeleton(joints)
    report=validate_skeleton(posed)
    if report["status"]!="pass":
        raise ValueError(report)
    matrices=global_joint_matrices(posed)
    rows={}
    for side in ("right","left"):
        volume=volumes[side]
        hand_index=indices[f"{side}_hand"]
        hand_joint=(matrices[hand_index][0][3],matrices[hand_index][1][3],matrices[hand_index][2][3])
        palm_socket=transform_point(matrices[hand_index],arms[side].hand_socket.position)
        roots=[]
        root_rows={}
        tips=[]
        for digit in range(1,6):
            root_index=indices[f"{side}_finger{digit}_1"]
            root=(matrices[root_index][0][3],matrices[root_index][1][3],matrices[root_index][2][3])
            tip=_tip_world(posed,indices,rig_evidence,side,digit)
            roots.append(root);tips.append(tip)
            root_rows[str(digit)]={
                "root_world":list(root),
                "root_surface_gap":_surface_gap(volume,root),
                "tip_world":list(tip),
                "open_tip_surface_gap":_surface_gap(volume,tip),
            }
        knuckles=[roots[index] for index in range(1,5)]
        knuckle_center=_mean(knuckles)
        spread=_sub(roots[4],roots[1])
        wrist_to_knuckles=_sub(knuckle_center,hand_joint)
        raw_normal=_normalize(_cross(spread,wrist_to_knuckles))

        center=volume["center"];axis=volume["axis"]
        assert isinstance(center,tuple) and isinstance(axis,tuple)
        t=_dot(_sub(knuckle_center,center),axis)
        centerline=_add(center,_mul(axis,t))
        outward=_normalize(_sub(knuckle_center,centerline))
        inward=_mul(outward,-1.0)
        if _dot(raw_normal,inward)<0.0:
            raw_normal=_mul(raw_normal,-1.0)

        root_gaps=[float(row["root_surface_gap"]["surface_gap_m"]) for row in root_rows.values()]
        tip_gaps=[float(row["open_tip_surface_gap"]["surface_gap_m"]) for row in root_rows.values()]
        rows[side]={
            "weapon_component":volume["name"],
            "hand_joint_world":list(hand_joint),
            "palm_socket_world":list(palm_socket),
            "palm_socket_surface_gap":_surface_gap(volume,palm_socket),
            "knuckle_center_world":list(knuckle_center),
            "knuckle_center_surface_gap":_surface_gap(volume,knuckle_center),
            "palm_plane_inward_normal_world":list(raw_normal),
            "desired_inward_grip_direction_world":list(inward),
            "palm_normal_to_grip_inward_angle_deg":_angle(raw_normal,inward),
            "root_surface_gap_m_range":[min(root_gaps),max(root_gaps)],
            "open_tip_surface_gap_m_range":[min(tip_gaps),max(tip_gaps)],
            "digits":root_rows,
            "surface_target":targets[side]["target_evidence"],
        }

    packet={
        "schema":SCHEMA,
        "rows":rows,
        "truth":{
            "diagnostic_only":True,
            "promotion_claim":False,
            "notes":[
                "Negative surface gaps mean a landmark is inside the approximated actual grip radial support volume.",
                "The palm-plane normal is derived from source-grounded proximal finger roots and the existing hand joint, then oriented toward the grip centerline.",
                "A large palm-normal angle indicates wrist orientation, not just clearance, is the likely blocker."
            ],
        },
    }
    return packet


if __name__=="__main__":
    packet=build_grip_palm_diagnostic()
    print(json.dumps(packet,indent=2,sort_keys=True))
