#!/usr/bin/env python3
"""Two-hand Sentinel rifle contact on the shared full-body hm08 humanoid rig.

v0.1 proved fixed-length two-hand contact with a temporary arm-only skeleton.
v0.2 consumes the Forge's shared 23-joint body-derived rig and its four-weight
skin proposal. Wrist pivots remain anatomical; explicit palm sockets define the
actual contact points against the real rifle grip sockets.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path

from native_attachment import Socket, TwoHandSocketAttachment, socket_contact_evidence
from native_geometry import Mesh, Vec3, bounds
from native_hm08_humanoid_rig import (
    SCHEMA as HUMANOID_RIG_SCHEMA,
    build_hm08_humanoid_skeleton,
    build_hm08_skin_weights,
    derive_hm08_rig_landmarks,
)
from native_hm08_rifle_contact_pose import (
    _add,
    _centroid,
    _distance,
    _mul,
    _quat_conjugate,
    _quat_from_to,
    _quat_mul,
    _quat_rotate,
    _solve_elbow,
    _sub,
)
from native_hm08_undersuit import _load_identity_body
from native_skin import Skeleton, global_joint_matrices, skin_vertices, transform_point, validate_skeleton
from native_weapon import sentinel_rifle, validate_weapon

SCHEMA = "axm.game-assets.hm08-rifle-contact-pose.v0.2"


@dataclass(frozen=True, slots=True)
class SharedRigArm:
    side: str
    shoulder: Vec3
    elbow: Vec3
    hand_joint: Vec3
    hand_contact: Vec3
    hand_socket: Socket
    upper_length_m: float
    forearm_hand_length_m: float
    hand_vertex_indices: tuple[int, ...]


def derive_shared_rig_arms(body_m: Mesh, landmarks: dict[str, Vec3]) -> dict[str, SharedRigArm]:
    lo, hi = bounds(body_m)
    height = hi[1] - lo[1]
    half_width = max(abs(lo[0]), abs(hi[0]), 1e-9)
    arms: dict[str, SharedRigArm] = {}
    for side, sign in (("right", 1.0), ("left", -1.0)):
        shoulder = landmarks[f"{side}_upper_arm"]
        elbow = landmarks[f"{side}_forearm"]
        hand_joint = landmarks[f"{side}_hand"]
        lateral = [sign * point[0] for point in body_m.vertices]
        hand_indices = [
            index for index, point in enumerate(body_m.vertices)
            if lateral[index] >= half_width*0.84
            and lo[1] + height*0.55 <= point[1] <= lo[1] + height*0.67
        ]
        if len(hand_indices) < 1000:
            raise ValueError(f"{side} shared-rig palm region too sparse: {len(hand_indices)}")
        hand_contact = _centroid(body_m, hand_indices)
        hand_socket = Socket(f"{side}_palm_grip", _sub(hand_contact, hand_joint))
        upper_length = _distance(shoulder, elbow)
        forearm_length = _distance(elbow, hand_joint)
        if not (0.16 <= upper_length <= 0.30 and 0.16 <= forearm_length <= 0.32):
            raise ValueError(f"{side} shared-rig arm lengths implausible: upper={upper_length} forearm={forearm_length}")
        arms[side] = SharedRigArm(
            side,
            shoulder,
            elbow,
            hand_joint,
            hand_contact,
            hand_socket,
            upper_length,
            forearm_length,
            tuple(hand_indices),
        )
    return arms


def _weapon_contact_targets(body_m: Mesh, arms: dict[str, SharedRigArm], rifle) -> dict[str, object]:
    lo, hi = bounds(body_m)
    height = hi[1] - lo[1]
    half_width = max(abs(lo[0]), abs(hi[0]), 1e-9)
    chest_points = [
        point for point in body_m.vertices
        if lo[1] + height*0.66 <= point[1] <= lo[1] + height*0.79
        and abs(point[0]) <= half_width*0.45
    ]
    if not chest_points:
        raise ValueError("cannot derive shared-rig chest front for rifle pose")
    chest_front_z = max(point[2] for point in chest_points)

    direction = (-0.989, 0.0, 0.148)
    weapon_rotation = _quat_from_to((1.0,0.0,0.0), direction)
    shoulder_y = (arms["right"].shoulder[1] + arms["left"].shoulder[1]) * 0.5
    primary_contact_target = (0.0, shoulder_y - height*0.060, chest_front_z + 0.040)
    primary_weapon_socket = rifle.sockets["primary_grip"]
    support_weapon_socket = rifle.sockets["support_grip"]
    primary_offset = _quat_rotate(weapon_rotation, primary_weapon_socket.position)
    weapon_translation = _sub(primary_contact_target, primary_offset)
    support_contact_target = _add(weapon_translation, _quat_rotate(weapon_rotation, support_weapon_socket.position))
    return {
        "translation": weapon_translation,
        "rotation": weapon_rotation,
        "scale": (1.0,1.0,1.0),
        "forward": direction,
        "primary_contact_target": primary_contact_target,
        "support_contact_target": support_contact_target,
        "chest_front_z": chest_front_z,
    }


def _joint_target_for_contact(contact_target: Vec3, hand_socket: Socket, hand_world_rotation) -> Vec3:
    return _sub(contact_target, _quat_rotate(hand_world_rotation, hand_socket.position))


def _solve_arm_rotations(arm: SharedRigArm, joint_target: Vec3, hand_world_rotation, *, sign: float):
    hint = _add(_add(arm.shoulder, _mul(_sub(joint_target, arm.shoulder), 0.50)), (sign*0.012, -0.045, -0.018))
    elbow = _solve_elbow(
        arm.shoulder,
        joint_target,
        arm.upper_length_m,
        arm.forearm_hand_length_m,
        hint,
    )
    bind_upper = _sub(arm.elbow, arm.shoulder)
    posed_upper = _sub(elbow, arm.shoulder)
    shoulder_rotation = _quat_from_to(bind_upper, posed_upper)
    bind_forearm = _sub(arm.hand_joint, arm.elbow)
    posed_forearm_world = _sub(joint_target, elbow)
    posed_forearm_local = _quat_rotate(_quat_conjugate(shoulder_rotation), posed_forearm_world)
    elbow_rotation = _quat_from_to(bind_forearm, posed_forearm_local)
    parent_global = _quat_mul(shoulder_rotation, elbow_rotation)
    hand_rotation = _quat_mul(_quat_conjugate(parent_global), hand_world_rotation)
    return elbow, shoulder_rotation, elbow_rotation, hand_rotation


def build_shared_rig_rifle_contact_pose(body_m: Mesh) -> tuple[Mesh, dict[str, object]]:
    rifle = sentinel_rifle()
    rifle_report = validate_weapon(rifle)
    if rifle_report["status"] != "pass":
        raise ValueError(f"rifle invalid before shared-rig contact pose: {rifle_report}")

    landmarks = derive_hm08_rig_landmarks(body_m)
    bind, rig_evidence, indices = build_hm08_humanoid_skeleton(body_m)
    weights, skin_evidence = build_hm08_skin_weights(body_m, bind, landmarks, indices)
    arms = derive_shared_rig_arms(body_m, landmarks)
    weapon_pose = _weapon_contact_targets(body_m, arms, rifle)
    weapon_rotation = weapon_pose["rotation"]
    assert isinstance(weapon_rotation, tuple)

    joints = list(bind.joints)
    arm_pose_evidence: dict[str, object] = {}
    for side, sign, contact_key, weapon_socket_key in (
        ("right", 1.0, "primary_contact_target", "primary_grip"),
        ("left", -1.0, "support_contact_target", "support_grip"),
    ):
        arm = arms[side]
        contact_target = weapon_pose[contact_key]
        assert isinstance(contact_target, tuple)
        weapon_socket = rifle.sockets[weapon_socket_key]
        desired_hand_rotation = _quat_mul(weapon_rotation, weapon_socket.rotation)
        joint_target = _joint_target_for_contact(contact_target, arm.hand_socket, desired_hand_rotation)
        reach = _distance(arm.shoulder, joint_target)
        maximum = arm.upper_length_m + arm.forearm_hand_length_m
        if reach > maximum + 1e-9:
            raise ValueError(f"{side} shared-rig hand target outside reach: {reach} > {maximum}")
        elbow, shoulder_rotation, elbow_rotation, hand_rotation = _solve_arm_rotations(
            arm, joint_target, desired_hand_rotation, sign=sign
        )
        upper_index = indices[f"{side}_upper_arm"]
        forearm_index = indices[f"{side}_forearm"]
        hand_index = indices[f"{side}_hand"]
        joints[upper_index] = replace(joints[upper_index], rotation=shoulder_rotation)
        joints[forearm_index] = replace(joints[forearm_index], rotation=elbow_rotation)
        joints[hand_index] = replace(joints[hand_index], rotation=hand_rotation)
        arm_pose_evidence[side] = {
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
        raise ValueError(f"shared-rig rifle pose skeleton invalid: {posed_report}")

    attachment = TwoHandSocketAttachment(
        primary_joint=indices["right_hand"],
        support_joint=indices["left_hand"],
        primary_hand_socket=arms["right"].hand_socket,
        support_hand_socket=arms["left"].hand_socket,
        primary_weapon_socket=rifle.sockets["primary_grip"],
        support_weapon_socket=rifle.sockets["support_grip"],
    )
    contact = socket_contact_evidence(posed, attachment)
    posed_vertices = skin_vertices(body_m, weights, bind, posed)
    posed_mesh = Mesh("sentinel_hm08_shared_rig_rifle_contact_v0_2", posed_vertices, list(body_m.faces))
    globals_ = global_joint_matrices(posed)

    hand_visual = {}
    for side in ("right","left"):
        centroid = _centroid(posed_mesh, arms[side].hand_vertex_indices)
        contact_position = contact[f"{'primary' if side=='right' else 'support'}_hand_contact_world_position"]
        target = tuple(float(value) for value in contact_position)
        hand_visual[side] = {
            "posed_hand_region_centroid": list(centroid),
            "hand_socket_world": list(target),
            "centroid_to_socket_error_m": _distance(centroid, target),
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

    rotated_arm_joints = {
        indices["right_upper_arm"], indices["right_forearm"], indices["right_hand"],
        indices["left_upper_arm"], indices["left_forearm"], indices["left_hand"],
    }
    stationary_max = 0.0
    moved_vertices = 0
    for vertex_index, (before, after) in enumerate(zip(body_m.vertices, posed_mesh.vertices)):
        distance = _distance(before, after)
        if distance > 1e-12:
            moved_vertices += 1
        active_rotated = any(
            joint in rotated_arm_joints and weight > 1e-9
            for joint, weight in zip(weights.joints[vertex_index], weights.weights[vertex_index])
        )
        if not active_rotated:
            stationary_max = max(stationary_max, distance)

    lo, hi = bounds(body_m)
    height = hi[1] - lo[1]
    head_indices = [i for i,p in enumerate(body_m.vertices) if p[1] >= lo[1] + height*0.84]
    lower_indices = [i for i,p in enumerate(body_m.vertices) if p[1] <= lo[1] + height*0.50]
    head_max = max(_distance(body_m.vertices[i], posed_mesh.vertices[i]) for i in head_indices)
    lower_max = max(_distance(body_m.vertices[i], posed_mesh.vertices[i]) for i in lower_indices)

    packet: dict[str, object] = {
        "schema": SCHEMA,
        "pose_id": "cross_chest_low_ready_shared_rig_v0.2",
        "shared_rig": {
            "schema": HUMANOID_RIG_SCHEMA,
            "joint_count": len(bind.joints),
            "joint_indices": indices,
            "skeleton_evidence": rig_evidence,
            "skin_evidence": skin_evidence,
        },
        "weapon": {
            "asset": rifle.name,
            "scale": list(weapon_pose["scale"]),
            "translation": list(weapon_pose["translation"]),
            "rotation": list(weapon_pose["rotation"]),
            "forward": list(weapon_pose["forward"]),
            "grip_socket_separation_m": _distance(rifle.sockets["primary_grip"].position, rifle.sockets["support_grip"].position),
        },
        "a_pose_palm_contact_separation_m": _distance(arms["right"].hand_contact, arms["left"].hand_contact),
        "arms": {
            side: {
                "shoulder": list(arm.shoulder),
                "bind_elbow": list(arm.elbow),
                "bind_hand_joint": list(arm.hand_joint),
                "bind_hand_contact": list(arm.hand_contact),
                "hand_socket": {"name":arm.hand_socket.name,"position":list(arm.hand_socket.position)},
                "upper_length_m": arm.upper_length_m,
                "forearm_hand_length_m": arm.forearm_hand_length_m,
                "hand_vertices": len(arm.hand_vertex_indices),
            }
            for side, arm in arms.items()
        },
        "pose": arm_pose_evidence,
        "contact": contact,
        "hand_visual_contact": hand_visual,
        "bone_lengths": bone_lengths,
        "moved_vertices": moved_vertices,
        "stationary_weight_region_max_displacement_m": stationary_max,
        "head_max_displacement_m": head_max,
        "lower_body_max_displacement_m": lower_max,
        "truth": {
            "uses_shared_full_body_rig": True,
            "temporary_arm_only_skeleton_used": False,
            "character_hand_sockets_explicit": True,
            "rifle_scaled_to_fake_contact": False,
            "canonical_body_mutated": False,
            "production_rig_claim": False,
            "production_skinning_claim": False,
            "runtime_ik_claim": False,
            "notes": [
                "The shared 23-joint hm08 humanoid rig owns the wrist pivots and four-weight skin proposal; this contact layer does not create a competing skeleton.",
                "Palm sockets are explicit local state on the hand joints, so weapon contact does not require moving anatomical wrist pivots to the grip point.",
                "Rifle grip contact is exact in rig/socket space. Visual hand-surface contact remains separately measured because proposal skin weights can still distort the hand region.",
                "Production promotion still requires visual deformation repair, fingers, wearable binding and real engine contact views."
            ],
        },
    }
    return posed_mesh, packet


def build_preferred_shared_rig_rifle_contact_pose():
    body_m, _uv, _state = _load_identity_body()
    return build_shared_rig_rifle_contact_pose(body_m)


if __name__ == "__main__":
    import json
    mesh, packet = build_preferred_shared_rig_rifle_contact_pose()
    print(json.dumps({"vertices":len(mesh.vertices),"faces":len(mesh.faces),**packet}, indent=2))
