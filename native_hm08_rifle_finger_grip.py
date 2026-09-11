#!/usr/bin/env python3
"""Finger-wrapped human-scale Sentinel rifle contact v0.5.

Run 2 ended with a source-grounded 53-joint finger rig, four-weight finger skin,
and a real human-scale rifle contact pose whose hands were still open. This
module keeps the v0.4 arm/weapon state fixed and changes only the 30 finger
joints. Each digit searches a bounded curl against the actual transformed
primary-grip or foregrip bounds. Knuckle/tip surface error and penetration are
measured before/after; Godot remains the visual promotion gate.
"""
from __future__ import annotations

from dataclasses import replace
from math import cos, sin, sqrt

from native_geometry import Mesh, Vec3, bounds
from native_hm08_finger_rig import build_hm08_finger_skeleton, build_hm08_finger_skin_weights
from native_hm08_rifle_contact_pose import (
    _add, _cross, _distance, _dot, _length, _mul, _normalize,
    _quat_conjugate, _quat_mul, _quat_rotate, _sub,
)
from native_hm08_rifle_contact_pose_v4 import build_segment_skin_rifle_contact_pose
from native_hm08_undersuit import _load_identity_body
from native_skin import (
    Joint, Skeleton, global_joint_matrices, normalize_quaternion, skin_vertices,
    transform_point, validate_skeleton,
)
from native_weapon_human_scale import sentinel_rifle_human_scale

SCHEMA = "axm.game-assets.hm08-rifle-finger-grip.v0.5"
SURFACE_PAD_M = 0.003


def _quat(row) -> tuple[float,float,float,float]:
    return tuple(float(value) for value in row)  # type: ignore[return-value]


def _axis_angle(axis: Vec3, angle: float):
    axis = _normalize(axis)
    half = angle * 0.5
    s = sin(half)
    return normalize_quaternion((axis[0]*s, axis[1]*s, axis[2]*s, cos(half)))


def _global_rotations(skeleton: Skeleton):
    result = []
    for joint in skeleton.joints:
        local = joint.rotation
        if joint.parent is None:
            result.append(local)
        else:
            result.append(_quat_mul(result[joint.parent], local))
    return result


def _local_to_weapon_world(local: Vec3, translation: Vec3, rotation) -> Vec3:
    return _add(translation, _quat_rotate(rotation, local))


def _world_to_weapon_local(world: Vec3, translation: Vec3, rotation) -> Vec3:
    return _quat_rotate(_quat_conjugate(rotation), _sub(world, translation))


def _aabb_sdf(point: Vec3, lo: Vec3, hi: Vec3) -> float:
    center = tuple((lo[i]+hi[i])*0.5 for i in range(3))
    half = tuple((hi[i]-lo[i])*0.5 for i in range(3))
    q = tuple(abs(point[i]-center[i])-half[i] for i in range(3))
    outside = sqrt(sum(max(value,0.0)**2 for value in q))
    inside = min(max(q), 0.0)
    return outside + inside


def _finger_points(skeleton: Skeleton, finger_indices: dict[str,int], tip_offsets: dict[str,object], side: str, digit: int):
    matrices = global_joint_matrices(skeleton)
    j2 = finger_indices[f"{side}_finger{digit}_2"]
    j3 = finger_indices[f"{side}_finger{digit}_3"]
    p2 = transform_point(matrices[j2], (0.0,0.0,0.0))
    p3 = transform_point(matrices[j3], (0.0,0.0,0.0))
    tip_local = tuple(float(v) for v in tip_offsets[f"{side}_finger{digit}_tip"])
    tip = transform_point(matrices[j3], tip_local)
    return p2, p3, tip


def _surface_score(points, translation: Vec3, rotation, box_lo: Vec3, box_hi: Vec3):
    desired = (0.010, 0.006, SURFACE_PAD_M)
    signed = []
    score = 0.0
    for point, pad in zip(points, desired):
        local = _world_to_weapon_local(point, translation, rotation)
        sdf = _aabb_sdf(local, box_lo, box_hi)
        signed.append(sdf)
        score += abs(sdf-pad)
        if sdf < -0.001:
            score += abs(sdf+0.001)*8.0
    return score, signed


def _arm_pose_on_finger_skeleton(bind: Skeleton, v4: dict[str,object]) -> Skeleton:
    indices = {joint.name:index for index,joint in enumerate(bind.joints)}
    joints = list(bind.joints)
    pose = v4["pose"]
    for side in ("right","left"):
        row = pose[side]
        for suffix, key in (("upper_arm","shoulder_rotation"),("forearm","elbow_rotation"),("hand","hand_rotation")):
            index = indices[f"{side}_{suffix}"]
            source = joints[index]
            joints[index] = replace(source, rotation=_quat(row[key]))
    result = Skeleton(joints)
    report = validate_skeleton(result)
    if report["status"] != "pass":
        raise ValueError(f"finger-rig arm pose invalid: {report}")
    return result


def _curl_profiles():
    return {
        1: (0.46,0.64,0.54),
        2: (0.58,0.86,0.72),
        3: (0.61,0.91,0.76),
        4: (0.63,0.94,0.78),
        5: (0.66,0.98,0.81),
    }


def build_finger_grip_rifle_contact_pose(body_m: Mesh) -> tuple[Mesh,dict[str,object]]:
    v4_mesh, v4 = build_segment_skin_rifle_contact_pose(body_m)
    bind, finger_indices, rig_evidence = build_hm08_finger_skeleton(body_m)
    weights, skin_evidence = build_hm08_finger_skin_weights(body_m, bind, finger_indices)
    arm_only = _arm_pose_on_finger_skeleton(bind, v4)
    arm_only_mesh = Mesh(
        "sentinel_hm08_finger_rig_arm_only_v0_5",
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
    digit_receipts = {}
    baseline_tip_errors = []
    final_tip_errors = []
    final_signed_all = []
    curled_digits = 0
    profiles = _curl_profiles()

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
                    key = (score, abs(strength-0.9))
                    best_key = (best[0], abs(best[1]-0.9))
                    if key < best_key:
                        best = (score, strength, direction, candidate_joints, signed)
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
                "curl_strength":best[1],
                "curl_direction":best[2],
                "improved_or_equal":final_score <= baseline_score + 1e-12,
            }

    posed = Skeleton(joints)
    posed_validation = validate_skeleton(posed)
    if posed_validation["status"] != "pass":
        raise ValueError(f"finger grip pose skeleton invalid: {posed_validation}")
    posed_mesh = Mesh(
        "sentinel_hm08_rifle_finger_grip_v0_5",
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
    digits_not_worse = sum(1 for row in digit_receipts.values() if row["improved_or_equal"])
    max_penetration = max(0.0, -min(final_signed_all)) if final_signed_all else 0.0
    summary = {
        "baseline_mean_tip_surface_error_m":baseline_mean,
        "final_mean_tip_surface_error_m":final_mean,
        "relative_tip_error":final_mean/max(baseline_mean,1e-12),
        "digits_not_worse":digits_not_worse,
        "curled_digits":curled_digits,
        "max_surface_penetration_m":max_penetration,
        "finger_influenced_vertices":len(finger_vertices),
        "finger_vertices_moved":finger_moved,
        "nonfinger_max_delta_from_arm_only_m":nonfinger_max,
    }

    packet = {
        "schema":SCHEMA,
        "pose_id":"cross_chest_low_ready_finger_wrap_v0.5",
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
            "production_grip_claim":False,
            "corrective_knuckle_shapes_claim":False,
            "automatic_visual_promotion":False,
            "notes":[
                "Each digit searches bounded curl strength/direction against the actual human-scale rifle grip component bounds in weapon-local space.",
                "The score rewards knuckle/tip approach to the grip surface and strongly penalizes penetration; no weapon scaling or palm-socket movement is allowed.",
                "Non-finger surface must remain identical to the arm-only 53-joint pose. Godot close views are required before this route can be promoted as a believable grip."
            ],
        },
    }
    return posed_mesh, packet


def build_preferred_finger_grip_rifle_contact_pose():
    body, _uv, _state = _load_identity_body()
    return build_finger_grip_rifle_contact_pose(body)


if __name__ == "__main__":
    import json
    mesh,packet = build_preferred_finger_grip_rifle_contact_pose()
    print(json.dumps({"vertices":len(mesh.vertices),"faces":len(mesh.faces),**packet},indent=2))
