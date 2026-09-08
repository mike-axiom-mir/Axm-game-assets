#!/usr/bin/env python3
"""Shared-rig two-hand contact with the human-scale Sentinel rifle v0.3.

v0.2 established the correct 23-joint rig + explicit palm-socket mechanics but
its real Godot view exposed a separate weapon-design fault: the legacy semantic
rifle was roughly 1.5 m long and dominated the character. v0.3 changes only the
weapon source to the authored human-scale v0.5 rifle. Rig, skin, palm sockets,
contact math and runtime scale=1 remain the same class of mechanism.
"""
from __future__ import annotations

from dataclasses import replace

from native_attachment import TwoHandSocketAttachment, socket_contact_evidence
from native_geometry import Mesh, bounds
from native_hm08_humanoid_rig import (
    SCHEMA as HUMANOID_RIG_SCHEMA,
    build_hm08_humanoid_skeleton,
    build_hm08_skin_weights,
    derive_hm08_rig_landmarks,
)
from native_hm08_rifle_contact_pose import _centroid, _distance, _quat_mul
from native_hm08_rifle_contact_pose_v2 import (
    _joint_target_for_contact,
    _solve_arm_rotations,
    _weapon_contact_targets,
    derive_shared_rig_arms,
)
from native_hm08_undersuit import _load_identity_body
from native_skin import Skeleton, global_joint_matrices, skin_vertices, transform_point, validate_skeleton
from native_weapon import validate_weapon
from native_weapon_human_scale import human_scale_weapon_evidence, sentinel_rifle_human_scale

SCHEMA = "axm.game-assets.hm08-rifle-contact-pose.v0.3"


def build_human_scale_rifle_contact_pose(body_m: Mesh) -> tuple[Mesh, dict[str, object]]:
    rifle = sentinel_rifle_human_scale()
    rifle_report = validate_weapon(rifle)
    dimensional = human_scale_weapon_evidence(rifle)
    if rifle_report["status"] != "pass" or dimensional["validation"]["status"] != "pass":
        raise ValueError(f"human-scale rifle invalid before contact pose: {rifle_report} {dimensional}")

    landmarks = derive_hm08_rig_landmarks(body_m)
    bind, rig_evidence, indices = build_hm08_humanoid_skeleton(body_m)
    weights, skin_evidence = build_hm08_skin_weights(body_m, bind, landmarks, indices)
    arms = derive_shared_rig_arms(body_m, landmarks)
    weapon_pose = _weapon_contact_targets(body_m, arms, rifle)
    weapon_rotation = weapon_pose["rotation"]
    assert isinstance(weapon_rotation, tuple)

    joints = list(bind.joints)
    pose_rows: dict[str, object] = {}
    for side, sign, target_key, socket_key in (
        ("right", 1.0, "primary_contact_target", "primary_grip"),
        ("left", -1.0, "support_contact_target", "support_grip"),
    ):
        arm = arms[side]
        contact_target = weapon_pose[target_key]
        assert isinstance(contact_target, tuple)
        socket = rifle.sockets[socket_key]
        desired_hand_rotation = _quat_mul(weapon_rotation, socket.rotation)
        joint_target = _joint_target_for_contact(contact_target, arm.hand_socket, desired_hand_rotation)
        reach = _distance(arm.shoulder, joint_target)
        maximum = arm.upper_length_m + arm.forearm_hand_length_m
        if reach > maximum + 1e-9:
            raise ValueError(f"{side} human-scale rifle target outside reach: {reach} > {maximum}")
        elbow, shoulder_rotation, elbow_rotation, hand_rotation = _solve_arm_rotations(
            arm, joint_target, desired_hand_rotation, sign=sign
        )
        upper_index = indices[f"{side}_upper_arm"]
        forearm_index = indices[f"{side}_forearm"]
        hand_index = indices[f"{side}_hand"]
        joints[upper_index] = replace(joints[upper_index], rotation=shoulder_rotation)
        joints[forearm_index] = replace(joints[forearm_index], rotation=elbow_rotation)
        joints[hand_index] = replace(joints[hand_index], rotation=hand_rotation)
        pose_rows[side] = {
            "contact_target": list(contact_target),
            "joint_target": list(joint_target),
            "elbow": list(elbow),
            "reach_m": reach,
            "maximum_reach_m": maximum,
            "hand_socket": {"name":arm.hand_socket.name,"position":list(arm.hand_socket.position)},
            "shoulder_rotation": list(shoulder_rotation),
            "elbow_rotation": list(elbow_rotation),
            "hand_rotation": list(hand_rotation),
        }

    posed = Skeleton(joints)
    posed_report = validate_skeleton(posed)
    if posed_report["status"] != "pass":
        raise ValueError(f"human-scale rifle pose skeleton invalid: {posed_report}")

    attachment = TwoHandSocketAttachment(
        primary_joint=indices["right_hand"],
        support_joint=indices["left_hand"],
        primary_hand_socket=arms["right"].hand_socket,
        support_hand_socket=arms["left"].hand_socket,
        primary_weapon_socket=rifle.sockets["primary_grip"],
        support_weapon_socket=rifle.sockets["support_grip"],
    )
    contact = socket_contact_evidence(posed, attachment)
    posed_mesh = Mesh(
        "sentinel_hm08_human_scale_rifle_contact_v0_3",
        skin_vertices(body_m, weights, bind, posed),
        list(body_m.faces),
    )
    globals_ = global_joint_matrices(posed)

    hand_visual = {}
    for side in ("right","left"):
        centroid = _centroid(posed_mesh, arms[side].hand_vertex_indices)
        key = "primary_hand_contact_world_position" if side == "right" else "support_hand_contact_world_position"
        socket_world = tuple(float(value) for value in contact[key])
        hand_visual[side] = {
            "posed_hand_region_centroid": list(centroid),
            "hand_socket_world": list(socket_world),
            "centroid_to_socket_error_m": _distance(centroid, socket_world),
        }

    bone_lengths = {}
    for side in ("right","left"):
        shoulder = transform_point(globals_[indices[f"{side}_upper_arm"]], (0.0,0.0,0.0))
        elbow = transform_point(globals_[indices[f"{side}_forearm"]], (0.0,0.0,0.0))
        hand = transform_point(globals_[indices[f"{side}_hand"]], (0.0,0.0,0.0))
        bone_lengths[side] = {
            "upper_bind_m": arms[side].upper_length_m,
            "upper_posed_m": _distance(shoulder, elbow),
            "forearm_bind_m": arms[side].forearm_hand_length_m,
            "forearm_posed_m": _distance(elbow, hand),
        }

    rotated = {
        indices["right_upper_arm"],indices["right_forearm"],indices["right_hand"],
        indices["left_upper_arm"],indices["left_forearm"],indices["left_hand"],
    }
    stationary_max = 0.0
    moved_vertices = 0
    for vertex_index, (before, after) in enumerate(zip(body_m.vertices, posed_mesh.vertices)):
        distance = _distance(before, after)
        if distance > 1e-12:
            moved_vertices += 1
        active = any(
            joint in rotated and weight > 1e-9
            for joint, weight in zip(weights.joints[vertex_index], weights.weights[vertex_index])
        )
        if not active:
            stationary_max = max(stationary_max, distance)

    lo, hi = bounds(body_m)
    height = hi[1] - lo[1]
    head_indices = [i for i,p in enumerate(body_m.vertices) if p[1] >= lo[1] + height*0.84]
    lower_indices = [i for i,p in enumerate(body_m.vertices) if p[1] <= lo[1] + height*0.50]
    head_max = max(_distance(body_m.vertices[i], posed_mesh.vertices[i]) for i in head_indices)
    lower_max = max(_distance(body_m.vertices[i], posed_mesh.vertices[i]) for i in lower_indices)

    packet: dict[str, object] = {
        "schema": SCHEMA,
        "pose_id": "cross_chest_low_ready_human_scale_rifle_v0.3",
        "shared_rig": {
            "schema": HUMANOID_RIG_SCHEMA,
            "joint_count": len(bind.joints),
            "joint_indices": indices,
            "skeleton_evidence": rig_evidence,
            "skin_evidence": skin_evidence,
        },
        "weapon": {
            "asset": rifle.name,
            "design_schema": dimensional["schema"],
            "source_length_m": dimensional["overall_length_m"],
            "scale": list(weapon_pose["scale"]),
            "translation": list(weapon_pose["translation"]),
            "rotation": list(weapon_pose["rotation"]),
            "forward": list(weapon_pose["forward"]),
            "grip_socket_separation_m": dimensional["grip_socket_separation_m"],
        },
        "a_pose_palm_contact_separation_m": _distance(arms["right"].hand_contact, arms["left"].hand_contact),
        "pose": pose_rows,
        "contact": contact,
        "hand_visual_contact": hand_visual,
        "bone_lengths": bone_lengths,
        "moved_vertices": moved_vertices,
        "stationary_weight_region_max_displacement_m": stationary_max,
        "head_max_displacement_m": head_max,
        "lower_body_max_displacement_m": lower_max,
        "truth": {
            "uses_shared_full_body_rig": True,
            "character_hand_sockets_explicit": True,
            "legacy_oversized_rifle_used": False,
            "rifle_scaled_to_fake_contact": False,
            "runtime_rifle_scale": [1.0,1.0,1.0],
            "canonical_body_mutated": False,
            "production_rig_claim": False,
            "production_skinning_claim": False,
            "runtime_ik_claim": False,
            "automatic_visual_promotion": False,
            "notes": [
                "v0.2 socket math was structurally valid but real Godot evidence rejected its 1.5 m legacy weapon and visible deformation. v0.3 changes only the weapon source to the human-scale v0.5 state.",
                "The human-scale rifle is authored at its new dimensions and still enters the pose at runtime scale 1.0.",
                "Shared-rig skinning, shoulder/elbow/wrist deformation and visible hand wrap remain independent visual quality gates."
            ],
        },
    }
    return posed_mesh, packet


def build_preferred_human_scale_rifle_contact_pose():
    body_m, _uv, _state = _load_identity_body()
    return build_human_scale_rifle_contact_pose(body_m)


if __name__ == "__main__":
    import json
    mesh, packet = build_preferred_human_scale_rifle_contact_pose()
    print(json.dumps({"vertices":len(mesh.vertices),"faces":len(mesh.faces),**packet}, indent=2))
