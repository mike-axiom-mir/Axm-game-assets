#!/usr/bin/env python3
"""Penetration-bounded Sentinel rifle finger grip v0.6.

v0.5 proved that the source-grounded 53-joint rig can move all ten digits toward
the real human-scale rifle grips, reducing mean fingertip surface error by about
two thirds. It also exposed a real defect: a candidate could buy a lower contact
score by penetrating the grip by almost 10 mm.

v0.6 preserves v0.5 as evidence and changes only candidate selection. Any curl
whose measured knuckle/tip points exceed the 4 mm penetration budget loses to
any feasible candidate before ordinary contact error is compared. The v0.4 arm
pose, weapon transform, finger skeleton, weights and curl profiles stay fixed.
"""
from __future__ import annotations

from dataclasses import replace

from native_geometry import Mesh, bounds
from native_hm08_finger_rig import build_hm08_finger_skeleton, build_hm08_finger_skin_weights
from native_hm08_rifle_contact_pose import _add, _cross, _distance, _dot, _length, _mul, _normalize, _quat_conjugate, _quat_rotate, _sub
from native_hm08_rifle_contact_pose_v4 import build_segment_skin_rifle_contact_pose
from native_hm08_rifle_finger_grip import (
    SURFACE_PAD_M,
    _arm_pose_on_finger_skeleton,
    _axis_angle,
    _curl_profiles,
    _finger_points,
    _global_rotations,
    _local_to_weapon_world,
    _quat,
    _surface_score,
)
from native_hm08_undersuit import _load_identity_body
from native_skin import Skeleton, global_joint_matrices, skin_vertices, transform_point, validate_skeleton
from native_weapon_human_scale import sentinel_rifle_human_scale

SCHEMA = "axm.game-assets.hm08-rifle-finger-grip.v0.6"
MAX_PENETRATION_M = 0.004


def _penetration(signed: list[float]) -> float:
    return max(0.0, -min(signed)) if signed else 0.0


def _candidate_key(score: float, signed: list[float], strength: float) -> tuple[float,float,float]:
    excess = max(0.0, _penetration(signed) - MAX_PENETRATION_M)
    return excess, score, abs(strength - 0.9)


def build_penetration_bounded_finger_grip(body_m: Mesh) -> tuple[Mesh,dict[str,object]]:
    _v4_mesh, v4 = build_segment_skin_rifle_contact_pose(body_m)
    bind, finger_indices, rig_evidence = build_hm08_finger_skeleton(body_m)
    weights, skin_evidence = build_hm08_finger_skin_weights(body_m, bind, finger_indices)
    arm_only = _arm_pose_on_finger_skeleton(bind, v4)
    arm_only_mesh = Mesh(
        "sentinel_hm08_finger_rig_arm_only_v0_6",
        skin_vertices(body_m, weights, bind, arm_only),
        list(body_m.faces),
    )

    rifle = sentinel_rifle_human_scale()
    weapon_row = v4["weapon"]
    translation = tuple(float(v) for v in weapon_row["translation"])
    rotation = _quat(weapon_row["rotation"])
    grip_axis_world = _quat_rotate(rotation, (0.0,1.0,0.0))
    component_for_side = {"right":"primary_grip", "left":"foregrip"}
    component_bounds = {name:bounds(rifle.components[name]) for name in component_for_side.values()}

    joints = list(arm_only.joints)
    arm_only_rotations = _global_rotations(arm_only)
    tip_offsets = rig_evidence["tip_local_offsets"]
    profiles = _curl_profiles()
    digit_receipts: dict[str,object] = {}
    baseline_tip_errors: list[float] = []
    final_tip_errors: list[float] = []
    final_signed_all: list[float] = []
    curled_digits = 0

    for side in ("right","left"):
        component_name = component_for_side[side]
        box_lo, box_hi = component_bounds[component_name]
        center_local = tuple((box_lo[i]+box_hi[i])*0.5 for i in range(3))
        center_world = _local_to_weapon_world(center_local, translation, rotation)
        for digit in range(1,6):
            current_base = Skeleton(list(joints))
            base_matrices = global_joint_matrices(current_base)
            first = finger_indices[f"{side}_finger{digit}_1"]
            second = finger_indices[f"{side}_finger{digit}_2"]
            first_world = transform_point(base_matrices[first], (0.0,0.0,0.0))
            second_world = transform_point(base_matrices[second], (0.0,0.0,0.0))
            segment = _sub(second_world, first_world)
            toward = _sub(center_world, first_world)
            radial = _sub(toward, _mul(grip_axis_world, _dot(toward, grip_axis_world)))
            if _length(radial) <= 1e-8:
                radial = toward
            bend_axis = _cross(segment, radial)
            if _length(bend_axis) <= 1e-8:
                bend_axis = _cross(segment, grip_axis_world)
            bend_axis = _normalize(bend_axis)

            local_axes = {}
            for segment_index in range(1,4):
                joint_index = finger_indices[f"{side}_finger{digit}_{segment_index}"]
                parent = current_base.joints[joint_index].parent
                parent_rotation = (0.0,0.0,0.0,1.0) if parent is None else arm_only_rotations[parent]
                local_axes[segment_index] = _quat_rotate(_quat_conjugate(parent_rotation), bend_axis)

            baseline_points = _finger_points(current_base, finger_indices, tip_offsets, side, digit)
            baseline_score, baseline_signed = _surface_score(baseline_points, translation, rotation, box_lo, box_hi)
            best = (baseline_score, 0.0, 1, list(joints), baseline_signed)
            best_key = _candidate_key(baseline_score, baseline_signed, 0.0)

            for direction in (-1,1):
                for step in range(1,33):
                    strength = step * 0.05
                    candidate_joints = list(joints)
                    for segment_index, base_angle in enumerate(profiles[digit], start=1):
                        joint_index = finger_indices[f"{side}_finger{digit}_{segment_index}"]
                        source = candidate_joints[joint_index]
                        candidate_joints[joint_index] = replace(
                            source,
                            rotation=_axis_angle(local_axes[segment_index], direction*base_angle*strength),
                        )
                    candidate = Skeleton(candidate_joints)
                    candidate_points = _finger_points(candidate, finger_indices, tip_offsets, side, digit)
                    score, signed = _surface_score(candidate_points, translation, rotation, box_lo, box_hi)
                    key = _candidate_key(score, signed, strength)
                    if key < best_key:
                        best = (score, strength, direction, candidate_joints, signed)
                        best_key = key

            joints = best[3]
            final_points = _finger_points(Skeleton(list(joints)), finger_indices, tip_offsets, side, digit)
            final_score, final_signed = _surface_score(final_points, translation, rotation, box_lo, box_hi)
            baseline_tip_error = abs(baseline_signed[-1]-SURFACE_PAD_M)
            final_tip_error = abs(final_signed[-1]-SURFACE_PAD_M)
            baseline_tip_errors.append(baseline_tip_error)
            final_tip_errors.append(final_tip_error)
            final_signed_all.extend(final_signed)
            if best[1] > 0.05:
                curled_digits += 1
            digit_receipts[f"{side}:{digit}"] = {
                "component":component_name,
                "baseline_score":baseline_score,
                "final_score":final_score,
                "baseline_signed_surface_m":baseline_signed,
                "final_signed_surface_m":final_signed,
                "baseline_tip_surface_error_m":baseline_tip_error,
                "final_tip_surface_error_m":final_tip_error,
                "baseline_penetration_m":_penetration(baseline_signed),
                "final_penetration_m":_penetration(final_signed),
                "curl_strength":best[1],
                "curl_direction":best[2],
                "improved_or_equal":final_score <= baseline_score + 1e-12,
                "within_penetration_budget":_penetration(final_signed) <= MAX_PENETRATION_M + 1e-12,
            }

    posed = Skeleton(joints)
    posed_validation = validate_skeleton(posed)
    if posed_validation["status"] != "pass":
        raise ValueError(f"v0.6 finger grip pose skeleton invalid: {posed_validation}")
    posed_mesh = Mesh(
        "sentinel_hm08_rifle_finger_grip_v0_6",
        skin_vertices(body_m, weights, bind, posed),
        list(body_m.faces),
    )

    base_joint_count = int(rig_evidence["base_joint_count"])
    finger_vertices = {
        index for index,(joint_row,weight_row) in enumerate(zip(weights.joints,weights.weights))
        if any(joint >= base_joint_count and weight > 1e-9 for joint,weight in zip(joint_row,weight_row))
    }
    nonfinger_max = 0.0
    finger_moved = 0
    for index,(before,after) in enumerate(zip(arm_only_mesh.vertices, posed_mesh.vertices)):
        movement = _distance(before,after)
        if index in finger_vertices:
            if movement > 1e-10:
                finger_moved += 1
        else:
            nonfinger_max = max(nonfinger_max, movement)

    baseline_mean = sum(baseline_tip_errors)/len(baseline_tip_errors)
    final_mean = sum(final_tip_errors)/len(final_tip_errors)
    max_penetration = max(0.0, -min(final_signed_all)) if final_signed_all else 0.0
    digits_not_worse = sum(1 for row in digit_receipts.values() if row["improved_or_equal"])
    budget_digits = sum(1 for row in digit_receipts.values() if row["within_penetration_budget"])
    worst = sorted(
        (
            {"digit":key,"penetration_m":row["final_penetration_m"],"tip_error_m":row["final_tip_surface_error_m"],"curl_strength":row["curl_strength"]}
            for key,row in digit_receipts.items()
        ),
        key=lambda row:(-row["penetration_m"],-row["tip_error_m"]),
    )
    summary = {
        "baseline_mean_tip_surface_error_m":baseline_mean,
        "final_mean_tip_surface_error_m":final_mean,
        "relative_tip_error":final_mean/max(baseline_mean,1e-12),
        "digits_not_worse":digits_not_worse,
        "digits_within_penetration_budget":budget_digits,
        "curled_digits":curled_digits,
        "max_surface_penetration_m":max_penetration,
        "penetration_budget_m":MAX_PENETRATION_M,
        "finger_influenced_vertices":len(finger_vertices),
        "finger_vertices_moved":finger_moved,
        "nonfinger_max_delta_from_arm_only_m":nonfinger_max,
        "worst_digits":worst[:4],
    }

    packet = {
        "schema":SCHEMA,
        "pose_id":"cross_chest_low_ready_finger_wrap_penetration_bounded_v0.6",
        "source_pose_schema":v4["schema"],
        "weapon":v4["weapon"],
        "arm_contact":v4["contact"],
        "arm_pose":v4["pose"],
        "finger_rig":rig_evidence,
        "finger_skin":skin_evidence,
        "digit_contact":digit_receipts,
        "contact_summary":summary,
        "posed_skeleton_validation":posed_validation,
        "truth":{
            "arm_pose_changed_from_v0_4":False,
            "weapon_transform_changed_from_v0_4":False,
            "source_grounded_53_joint_rig_used":True,
            "finger_pose_only_changed_variable":True,
            "v0_5_preserved_as_evidence":True,
            "production_grip_claim":False,
            "corrective_knuckle_shapes_claim":False,
            "automatic_visual_promotion":False,
            "notes":[
                "v0.5 proved contact-error reduction but allowed nearly 10 mm grip penetration. v0.6 preserves that attempt and makes penetration budget the first candidate-selection key.",
                "A curl deeper than 4 mm into the measured grip bounds cannot beat a feasible curl merely by improving tip distance.",
                "Arm pose, weapon transform, finger source pivots/weights and curl profiles remain unchanged from the v0.5 experiment. Godot A/B remains mandatory before promotion."
            ],
        },
    }
    return posed_mesh,packet


def build_preferred_penetration_bounded_finger_grip():
    body,_uv,_state = _load_identity_body()
    return build_penetration_bounded_finger_grip(body)


if __name__ == "__main__":
    import json
    mesh,packet = build_preferred_penetration_bounded_finger_grip()
    print(json.dumps({"vertices":len(mesh.vertices),"faces":len(mesh.faces),**packet},indent=2))
