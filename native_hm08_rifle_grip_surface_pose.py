#!/usr/bin/env python3
"""Grip-surface palm placement + finger wrap for Sentinel v0.7.

Run 2's hand-socket contact used weapon sockets located inside the modeled grip
volumes. That is a valid attachment reference, but aligning a palm centroid to
that internal reference leaves some open fingers embedded before curl. Run 3
v0.5/v0.6 exposed the fault directly: right middle finger began 16.6 mm inside
the primary grip.

v0.7 keeps the authored rifle and its transform fixed, but treats the internal
socket as an attachment reference rather than a palm surface. For each hand it
searches the four lateral faces of the actual grip component AABB, solves the
shared anatomical arm to that candidate, and chooses the reachable surface that
minimizes open-finger penetration first and surface distance second. Only then
is the source-grounded 53-joint finger curl applied with the 4 mm penetration
budget. No weapon scaling or canonical body mutation is allowed.
"""
from __future__ import annotations

from dataclasses import replace

from native_geometry import Mesh, bounds
from native_hm08_finger_rig import build_hm08_finger_skeleton, build_hm08_finger_skin_weights
from native_hm08_humanoid_rig import derive_hm08_rig_landmarks
from native_hm08_rifle_contact_pose import _add, _cross, _distance, _dot, _length, _mul, _normalize, _quat_conjugate, _quat_mul, _quat_rotate, _sub
from native_hm08_rifle_contact_pose_v2 import _joint_target_for_contact, _solve_arm_rotations, derive_shared_rig_arms
from native_hm08_rifle_contact_pose_v4 import build_segment_skin_rifle_contact_pose
from native_hm08_rifle_finger_grip import (
    SURFACE_PAD_M,
    _axis_angle,
    _curl_profiles,
    _finger_points,
    _global_rotations,
    _local_to_weapon_world,
    _quat,
    _surface_score,
)
from native_hm08_rifle_finger_grip_v2 import MAX_PENETRATION_M, _candidate_key, _penetration
from native_hm08_undersuit import _load_identity_body
from native_skin import Skeleton, skin_vertices, validate_skeleton
from native_weapon_human_scale import sentinel_rifle_human_scale

SCHEMA = "axm.game-assets.hm08-rifle-grip-surface-pose.v0.7"
PALM_SURFACE_CLEARANCE_M = 0.010


def _set_arm_pose(bind: Skeleton, indices: dict[str,int], side: str, shoulder_rotation, elbow_rotation, hand_rotation) -> Skeleton:
    joints = list(bind.joints)
    for suffix, rotation in (("upper_arm",shoulder_rotation),("forearm",elbow_rotation),("hand",hand_rotation)):
        index = indices[f"{side}_{suffix}"]
        joints[index] = replace(joints[index], rotation=rotation)
    return Skeleton(joints)


def _apply_arm_rows(bind: Skeleton, indices: dict[str,int], rows: dict[str,dict[str,object]]) -> Skeleton:
    joints = list(bind.joints)
    for side in ("right","left"):
        row = rows[side]
        for suffix,key in (("upper_arm","shoulder_rotation"),("forearm","elbow_rotation"),("hand","hand_rotation")):
            index = indices[f"{side}_{suffix}"]
            joints[index] = replace(joints[index], rotation=_quat(row[key]))
    result = Skeleton(joints)
    report = validate_skeleton(result)
    if report["status"] != "pass":
        raise ValueError(f"surface-contact arm skeleton invalid: {report}")
    return result


def _component_surface_candidates(component_lo, component_hi, socket_y: float):
    cx = (component_lo[0]+component_hi[0])*0.5
    cz = (component_lo[2]+component_hi[2])*0.5
    return [
        ("x_min", (component_lo[0]-PALM_SURFACE_CLEARANCE_M, socket_y, cz)),
        ("x_max", (component_hi[0]+PALM_SURFACE_CLEARANCE_M, socket_y, cz)),
        ("z_min", (cx, socket_y, component_lo[2]-PALM_SURFACE_CLEARANCE_M)),
        ("z_max", (cx, socket_y, component_hi[2]+PALM_SURFACE_CLEARANCE_M)),
    ]


def _finger_surface_summary(skeleton: Skeleton, finger_indices, tip_offsets, side: str, translation, rotation, box_lo, box_hi):
    signed_all = []
    score_sum = 0.0
    tip_errors = []
    for digit in range(1,6):
        points = _finger_points(skeleton, finger_indices, tip_offsets, side, digit)
        score,signed = _surface_score(points,translation,rotation,box_lo,box_hi)
        score_sum += score
        signed_all.extend(signed)
        tip_errors.append(abs(signed[-1]-SURFACE_PAD_M))
    return {
        "max_penetration_m":_penetration(signed_all),
        "score_sum":score_sum,
        "mean_tip_surface_error_m":sum(tip_errors)/len(tip_errors),
        "signed_samples":signed_all,
    }


def build_grip_surface_finger_pose(body_m: Mesh) -> tuple[Mesh,dict[str,object]]:
    _v4_mesh,v4 = build_segment_skin_rifle_contact_pose(body_m)
    bind,finger_indices,rig_evidence = build_hm08_finger_skeleton(body_m)
    weights,skin_evidence = build_hm08_finger_skin_weights(body_m,bind,finger_indices)
    indices = {joint.name:index for index,joint in enumerate(bind.joints)}
    landmarks = derive_hm08_rig_landmarks(body_m)
    arms = derive_shared_rig_arms(body_m,landmarks)

    rifle = sentinel_rifle_human_scale()
    weapon = v4["weapon"]
    translation = tuple(float(v) for v in weapon["translation"])
    weapon_rotation = _quat(weapon["rotation"])
    component_for_side = {"right":"primary_grip","left":"foregrip"}
    socket_for_side = {"right":"primary_grip","left":"support_grip"}
    tip_offsets = rig_evidence["tip_local_offsets"]

    original_arm_pose = _apply_arm_rows(bind,indices,v4["pose"])
    surface_rows: dict[str,dict[str,object]] = {}
    surface_search: dict[str,object] = {}

    for side,sign in (("right",1.0),("left",-1.0)):
        component_name = component_for_side[side]
        socket_name = socket_for_side[side]
        component_lo,component_hi = bounds(rifle.components[component_name])
        weapon_socket = rifle.sockets[socket_name]
        desired_hand_rotation = _quat_mul(weapon_rotation,weapon_socket.rotation)
        arm = arms[side]

        original_summary = _finger_surface_summary(
            original_arm_pose,finger_indices,tip_offsets,side,translation,weapon_rotation,component_lo,component_hi
        )
        candidates = []
        best = None
        for face_name,local_contact in _component_surface_candidates(component_lo,component_hi,weapon_socket.position[1]):
            contact_world = _local_to_weapon_world(local_contact,translation,weapon_rotation)
            joint_target = _joint_target_for_contact(contact_world,arm.hand_socket,desired_hand_rotation)
            reach = _distance(arm.shoulder,joint_target)
            maximum = arm.upper_length_m+arm.forearm_hand_length_m
            if reach > maximum+1e-9:
                candidates.append({"face":face_name,"reachable":False,"reach_m":reach,"maximum_reach_m":maximum})
                continue
            elbow,shoulder_rotation,elbow_rotation,hand_rotation = _solve_arm_rotations(
                arm,joint_target,desired_hand_rotation,sign=sign
            )
            candidate_skeleton = _set_arm_pose(bind,indices,side,shoulder_rotation,elbow_rotation,hand_rotation)
            report = validate_skeleton(candidate_skeleton)
            if report["status"] != "pass":
                continue
            finger_summary = _finger_surface_summary(
                candidate_skeleton,finger_indices,tip_offsets,side,translation,weapon_rotation,component_lo,component_hi
            )
            movement = _distance(contact_world,tuple(float(v) for v in v4["pose"][side]["contact_target"]))
            row = {
                "face":face_name,
                "reachable":True,
                "local_contact":list(local_contact),
                "world_contact":list(contact_world),
                "joint_target":list(joint_target),
                "elbow":list(elbow),
                "reach_m":reach,
                "maximum_reach_m":maximum,
                "contact_shift_from_internal_socket_m":movement,
                "shoulder_rotation":list(shoulder_rotation),
                "elbow_rotation":list(elbow_rotation),
                "hand_rotation":list(hand_rotation),
                "open_finger":finger_summary,
            }
            candidates.append(row)
            key = (finger_summary["max_penetration_m"],finger_summary["score_sum"],movement,face_name)
            if best is None or key < best[0]:
                best = (key,row)
        if best is None:
            raise ValueError(f"no reachable grip surface for {side}")
        selected = best[1]
        surface_rows[side] = selected
        surface_search[side] = {
            "component":component_name,
            "internal_socket_local":list(weapon_socket.position),
            "original_open_finger":original_summary,
            "selected_face":selected["face"],
            "selected_open_finger":selected["open_finger"],
            "candidates":candidates,
        }

    arm_surface_pose = _apply_arm_rows(bind,indices,surface_rows)
    arm_only_mesh = Mesh(
        "sentinel_hm08_grip_surface_arm_pose_v0_7",
        skin_vertices(body_m,weights,bind,arm_surface_pose),
        list(body_m.faces),
    )
    joints = list(arm_surface_pose.joints)
    arm_rotations = _global_rotations(arm_surface_pose)
    grip_axis_world = _quat_rotate(weapon_rotation,(0.0,1.0,0.0))
    profiles = _curl_profiles()
    digit_receipts: dict[str,object] = {}
    final_signed_all = []
    baseline_tip_errors = []
    final_tip_errors = []
    curled_digits = 0

    for side in ("right","left"):
        component_name = component_for_side[side]
        box_lo,box_hi = bounds(rifle.components[component_name])
        center_local = tuple((box_lo[i]+box_hi[i])*0.5 for i in range(3))
        center_world = _local_to_weapon_world(center_local,translation,weapon_rotation)
        for digit in range(1,6):
            current_base = Skeleton(list(joints))
            matrices = __import__("native_skin").global_joint_matrices(current_base)
            first = finger_indices[f"{side}_finger{digit}_1"]
            second = finger_indices[f"{side}_finger{digit}_2"]
            first_world = __import__("native_skin").transform_point(matrices[first],(0.0,0.0,0.0))
            second_world = __import__("native_skin").transform_point(matrices[second],(0.0,0.0,0.0))
            segment = _sub(second_world,first_world)
            toward = _sub(center_world,first_world)
            radial = _sub(toward,_mul(grip_axis_world,_dot(toward,grip_axis_world)))
            if _length(radial)<=1e-8:
                radial=toward
            bend_axis=_cross(segment,radial)
            if _length(bend_axis)<=1e-8:
                bend_axis=_cross(segment,grip_axis_world)
            bend_axis=_normalize(bend_axis)
            local_axes={}
            for segment_index in range(1,4):
                joint_index=finger_indices[f"{side}_finger{digit}_{segment_index}"]
                parent=current_base.joints[joint_index].parent
                parent_rotation=(0.0,0.0,0.0,1.0) if parent is None else arm_rotations[parent]
                local_axes[segment_index]=_quat_rotate(_quat_conjugate(parent_rotation),bend_axis)

            baseline_points=_finger_points(current_base,finger_indices,tip_offsets,side,digit)
            baseline_score,baseline_signed=_surface_score(baseline_points,translation,weapon_rotation,box_lo,box_hi)
            best=(baseline_score,0.0,1,list(joints),baseline_signed)
            best_key=_candidate_key(baseline_score,baseline_signed,0.0)
            for direction in (-1,1):
                for step in range(1,33):
                    strength=step*0.05
                    candidate_joints=list(joints)
                    for segment_index,base_angle in enumerate(profiles[digit],start=1):
                        joint_index=finger_indices[f"{side}_finger{digit}_{segment_index}"]
                        candidate_joints[joint_index]=replace(
                            candidate_joints[joint_index],
                            rotation=_axis_angle(local_axes[segment_index],direction*base_angle*strength),
                        )
                    candidate=Skeleton(candidate_joints)
                    candidate_points=_finger_points(candidate,finger_indices,tip_offsets,side,digit)
                    score,signed=_surface_score(candidate_points,translation,weapon_rotation,box_lo,box_hi)
                    key=_candidate_key(score,signed,strength)
                    if key<best_key:
                        best=(score,strength,direction,candidate_joints,signed)
                        best_key=key
            joints=best[3]
            final_points=_finger_points(Skeleton(list(joints)),finger_indices,tip_offsets,side,digit)
            final_score,final_signed=_surface_score(final_points,translation,weapon_rotation,box_lo,box_hi)
            baseline_tip=abs(baseline_signed[-1]-SURFACE_PAD_M)
            final_tip=abs(final_signed[-1]-SURFACE_PAD_M)
            baseline_tip_errors.append(baseline_tip)
            final_tip_errors.append(final_tip)
            final_signed_all.extend(final_signed)
            if best[1]>0.05:
                curled_digits+=1
            digit_receipts[f"{side}:{digit}"]={
                "component":component_name,
                "baseline_penetration_m":_penetration(baseline_signed),
                "final_penetration_m":_penetration(final_signed),
                "baseline_tip_surface_error_m":baseline_tip,
                "final_tip_surface_error_m":final_tip,
                "baseline_score":baseline_score,
                "final_score":final_score,
                "curl_strength":best[1],
                "curl_direction":best[2],
                "within_penetration_budget":_penetration(final_signed)<=MAX_PENETRATION_M+1e-12,
            }

    posed=Skeleton(joints)
    posed_validation=validate_skeleton(posed)
    if posed_validation["status"]!="pass":
        raise ValueError(f"grip surface finger pose invalid: {posed_validation}")
    posed_mesh=Mesh(
        "sentinel_hm08_grip_surface_finger_pose_v0_7",
        skin_vertices(body_m,weights,bind,posed),
        list(body_m.faces),
    )

    base_joint_count=int(rig_evidence["base_joint_count"])
    finger_vertices={
        index for index,(joint_row,weight_row) in enumerate(zip(weights.joints,weights.weights))
        if any(joint>=base_joint_count and weight>1e-9 for joint,weight in zip(joint_row,weight_row))
    }
    nonfinger_delta=0.0
    finger_moved=0
    for index,(before,after) in enumerate(zip(arm_only_mesh.vertices,posed_mesh.vertices)):
        delta=_distance(before,after)
        if index in finger_vertices:
            if delta>1e-10:
                finger_moved+=1
        else:
            nonfinger_delta=max(nonfinger_delta,delta)

    baseline_mean=sum(baseline_tip_errors)/len(baseline_tip_errors)
    final_mean=sum(final_tip_errors)/len(final_tip_errors)
    max_penetration=_penetration(final_signed_all)
    budget_digits=sum(1 for row in digit_receipts.values() if row["within_penetration_budget"])
    original_max=max(float(surface_search[side]["original_open_finger"]["max_penetration_m"]) for side in ("right","left"))
    selected_open_max=max(float(surface_search[side]["selected_open_finger"]["max_penetration_m"]) for side in ("right","left"))
    summary={
        "original_internal_socket_open_finger_max_penetration_m":original_max,
        "surface_contact_open_finger_max_penetration_m":selected_open_max,
        "baseline_mean_tip_surface_error_m":baseline_mean,
        "final_mean_tip_surface_error_m":final_mean,
        "relative_tip_error":final_mean/max(baseline_mean,1e-12),
        "digits_within_penetration_budget":budget_digits,
        "max_surface_penetration_m":max_penetration,
        "penetration_budget_m":MAX_PENETRATION_M,
        "curled_digits":curled_digits,
        "finger_vertices_moved":finger_moved,
        "nonfinger_max_delta_from_surface_arm_pose_m":nonfinger_delta,
    }
    packet={
        "schema":SCHEMA,
        "pose_id":"cross_chest_grip_surface_finger_wrap_v0.7",
        "source_pose_schema":v4["schema"],
        "weapon":v4["weapon"],
        "surface_contact_search":surface_search,
        "selected_arm_pose":surface_rows,
        "digit_contact":digit_receipts,
        "finger_rig":rig_evidence,
        "finger_skin":skin_evidence,
        "contact_summary":summary,
        "posed_skeleton_validation":posed_validation,
        "truth":{
            "weapon_transform_changed_from_v0_4":False,
            "internal_weapon_sockets_preserved":True,
            "internal_socket_reinterpreted_as_palm_surface":False,
            "palm_surface_derived_from_grip_geometry":True,
            "source_grounded_53_joint_rig_used":True,
            "production_grip_claim":False,
            "corrective_knuckle_shapes_claim":False,
            "automatic_visual_promotion":False,
            "notes":[
                "The authored internal weapon sockets remain untouched. v0.7 adds a separate derived palm-surface contact target from the real grip geometry.",
                "Four lateral grip faces are tested per hand; reachability, open-finger penetration and surface error decide which face is used before finger curl.",
                "This explicitly repairs the evidence that right middle finger began 16.6 mm inside the primary grip under the old palm-centroid-to-internal-socket interpretation.",
                "Godot close-view A/B is still required before the surface-contact + finger-wrap route can be promoted."
            ],
        },
    }
    return posed_mesh,packet


def build_preferred_grip_surface_finger_pose():
    body,_uv,_state=_load_identity_body()
    return build_grip_surface_finger_pose(body)


if __name__=="__main__":
    import json
    mesh,packet=build_preferred_grip_surface_finger_pose()
    print(json.dumps({"vertices":len(mesh.vertices),"faces":len(mesh.faces),**packet},indent=2))
