#!/usr/bin/env python3
"""Two-hand Sentinel rifle pose on the real full-body humanoid rig.

The 23-joint body-derived skeleton remains the sole deformation authority.
Anatomical wrist/hand joints are never moved into the palm just to satisfy a
weapon grip. Instead, measured palm centroids become explicit character-side
hand sockets local to those joints, paired with the rifle's real grip sockets.

This joins full-body deformation and two-hand attachment into one motion truth
without adding contact-only bones. Production skinning, fingers, twist bones,
wearable deformation and runtime IK remain later gates.
"""
from __future__ import annotations

from dataclasses import replace

from native_attachment import Socket, TwoHandSocketAttachment, socket_contact_evidence
from native_geometry import Mesh, bounds
from native_hm08_humanoid_rig import (
    build_preferred_hm08_humanoid_rig,
    deformation_evidence,
    derive_hm08_rig_landmarks,
)
from native_hm08_rifle_contact_pose import (
    ArmChain,
    _centroid,
    _distance,
    _mul,
    _quat_conjugate,
    _quat_from_to,
    _quat_mul,
    _quat_rotate,
    _solve_elbow,
    _sub,
    _world_weapon_pose,
)
from native_skin import Skeleton, global_joint_matrices, skin_vertices, transform_point, validate_skeleton
from native_weapon import sentinel_rifle, validate_weapon

SCHEMA = "axm.game-assets.hm08-full-rifle-pose.v0.2"


def _add(a, b):
    return a[0] + b[0], a[1] + b[1], a[2] + b[2]


def _hand_indices(body: Mesh, *, side: str) -> tuple[int, ...]:
    lo, hi = bounds(body)
    height = hi[1] - lo[1]
    half_width = max(abs(lo[0]), abs(hi[0]), 1e-9)
    sign = 1.0 if side == "right" else -1.0
    rows = [
        index for index, point in enumerate(body.vertices)
        if sign * point[0] >= half_width * 0.84
        and lo[1] + height * 0.55 <= point[1] <= lo[1] + height * 0.67
    ]
    if len(rows) < 1000:
        raise ValueError(f"{side} hand region unexpectedly sparse: {len(rows)}")
    return tuple(rows)


def _character_hand_sockets(
    body: Mesh,
    landmarks: dict[str, tuple[float, float, float]],
) -> tuple[dict[str, Socket], dict[str, tuple[float, float, float]], dict[str, tuple[int, ...]]]:
    sockets: dict[str, Socket] = {}
    palms: dict[str, tuple[float, float, float]] = {}
    hand_sets: dict[str, tuple[int, ...]] = {}
    for side in ("right", "left"):
        hand_sets[side] = _hand_indices(body, side=side)
        palm = _centroid(body, hand_sets[side])
        wrist = landmarks[f"{side}_hand"]
        palms[side] = palm
        sockets[side] = Socket(
            f"{side}_palm_grip",
            position=_sub(palm, wrist),
        )
    return sockets, palms, hand_sets


def _contact_chains(
    landmarks: dict[str, tuple[float, float, float]],
    palms: dict[str, tuple[float, float, float]],
    hand_sets: dict[str, tuple[int, ...]],
) -> dict[str, ArmChain]:
    chains = {}
    for side in ("right", "left"):
        shoulder = landmarks[f"{side}_upper_arm"]
        elbow = landmarks[f"{side}_forearm"]
        palm = palms[side]
        chains[side] = ArmChain(
            side=side,
            shoulder=shoulder,
            elbow=elbow,
            hand=palm,
            upper_length_m=_distance(shoulder, elbow),
            forearm_hand_length_m=_distance(elbow, palm),
            hand_vertex_indices=hand_sets[side],
        )
    return chains


def _solve_full_arm(
    joints,
    indices: dict[str, int],
    landmarks: dict[str, tuple[float, float, float]],
    hand_socket: Socket,
    chains: dict[str, ArmChain],
    weapon_pose: dict[str, object],
    rifle,
    *,
    side: str,
    sign: float,
    target_key: str,
    socket_key: str,
) -> dict[str, object]:
    chain = chains[side]
    palm_target = weapon_pose[target_key]
    weapon_rotation = weapon_pose["rotation"]
    assert isinstance(palm_target, tuple) and isinstance(weapon_rotation, tuple)

    # Desired character hand-socket world rotation equals the target weapon
    # socket world rotation. Character hand sockets currently use identity local
    # rotation, but the explicit multiplication keeps the relation inspectable.
    desired_hand_socket_world_rotation = _quat_mul(
        weapon_rotation,
        rifle.sockets[socket_key].rotation,
    )
    desired_hand_joint_world_rotation = _quat_mul(
        desired_hand_socket_world_rotation,
        _quat_conjugate(hand_socket.rotation),
    )

    wrist_bind = landmarks[f"{side}_hand"]
    rotated_palm_offset = _quat_rotate(desired_hand_joint_world_rotation, hand_socket.position)
    wrist_target = _sub(palm_target, rotated_palm_offset)

    shoulder = landmarks[f"{side}_upper_arm"]
    elbow_bind = landmarks[f"{side}_forearm"]
    upper_length = _distance(shoulder, elbow_bind)
    forearm_length = _distance(elbow_bind, wrist_bind)
    line_hint = _add(shoulder, _mul(_sub(wrist_target, shoulder), 0.50))
    hint = _add(line_hint, (sign * 0.010, -0.040, -0.020))
    elbow = _solve_elbow(shoulder, wrist_target, upper_length, forearm_length, hint)

    bind_upper = _sub(elbow_bind, shoulder)
    posed_upper = _sub(elbow, shoulder)
    shoulder_rotation = _quat_from_to(bind_upper, posed_upper)

    bind_forearm = _sub(wrist_bind, elbow_bind)
    posed_forearm_world = _sub(wrist_target, elbow)
    posed_forearm_local = _quat_rotate(_quat_conjugate(shoulder_rotation), posed_forearm_world)
    elbow_rotation = _quat_from_to(bind_forearm, posed_forearm_local)
    parent_global = _quat_mul(shoulder_rotation, elbow_rotation)
    hand_rotation = _quat_mul(_quat_conjugate(parent_global), desired_hand_joint_world_rotation)

    upper_index = indices[f"{side}_upper_arm"]
    forearm_index = indices[f"{side}_forearm"]
    hand_index = indices[f"{side}_hand"]
    joints[upper_index] = replace(joints[upper_index], rotation=shoulder_rotation)
    joints[forearm_index] = replace(joints[forearm_index], rotation=elbow_rotation)
    joints[hand_index] = replace(joints[hand_index], rotation=hand_rotation)

    return {
        "palm_target": list(palm_target),
        "wrist_target": list(wrist_target),
        "solved_elbow": list(elbow),
        "upper_bind_length_m": upper_length,
        "forearm_bind_length_m": forearm_length,
        "character_hand_socket": {
            "name": hand_socket.name,
            "position": list(hand_socket.position),
            "rotation": list(hand_socket.rotation),
        },
        "shoulder_rotation": list(shoulder_rotation),
        "elbow_rotation": list(elbow_rotation),
        "hand_rotation": list(hand_rotation),
    }


def build_hm08_full_rifle_pose() -> tuple[Mesh, dict[str, object]]:
    body, bind, weights, _diagnostic, rig_evidence = build_preferred_hm08_humanoid_rig()
    landmarks = derive_hm08_rig_landmarks(body)
    indices = dict(rig_evidence["joint_indices"])
    hand_sockets, palms, hand_sets = _character_hand_sockets(body, landmarks)
    chains = _contact_chains(landmarks, palms, hand_sets)

    rifle = sentinel_rifle()
    weapon_report = validate_weapon(rifle)
    if weapon_report["status"] != "pass":
        raise ValueError(f"rifle invalid before full-rig contact: {weapon_report}")
    weapon_pose = _world_weapon_pose(body, chains, rifle)

    joints = list(bind.joints)
    pose_rows = {
        "right": _solve_full_arm(
            joints, indices, landmarks, hand_sockets["right"], chains, weapon_pose, rifle,
            side="right", sign=1.0, target_key="primary_target", socket_key="primary_grip",
        ),
        "left": _solve_full_arm(
            joints, indices, landmarks, hand_sockets["left"], chains, weapon_pose, rifle,
            side="left", sign=-1.0, target_key="support_target", socket_key="support_grip",
        ),
    }
    posed = Skeleton(joints)
    posed_report = validate_skeleton(posed)
    if posed_report["status"] != "pass":
        raise ValueError(f"full-rig rifle pose invalid: {posed_report}")

    attachment = TwoHandSocketAttachment(
        primary_joint=indices["right_hand"],
        support_joint=indices["left_hand"],
        primary_hand_socket=hand_sockets["right"],
        support_hand_socket=hand_sockets["left"],
        primary_weapon_socket=rifle.sockets["primary_grip"],
        support_weapon_socket=rifle.sockets["support_grip"],
    )
    contact = socket_contact_evidence(posed, attachment)
    posed_vertices = skin_vertices(body, weights, bind, posed)
    posed_mesh = Mesh("sentinel_hm08_full_rig_rifle_pose_v0_2", posed_vertices, list(body.faces))

    hand_contact_world = {
        "right": tuple(float(value) for value in contact["primary_hand_contact_world_position"]),
        "left": tuple(float(value) for value in contact["support_hand_contact_world_position"]),
    }
    hand_geometry = {}
    for side in ("right", "left"):
        centroid = _centroid(posed_mesh, hand_sets[side])
        hand_geometry[side] = {
            "character_socket_world": list(hand_contact_world[side]),
            "posed_hand_centroid": list(centroid),
            "centroid_to_socket_error_m": _distance(centroid, hand_contact_world[side]),
            "hand_vertices": len(hand_sets[side]),
        }

    contact_weapon_world = contact["weapon_world"]
    derived_weapon_translation = (
        float(contact_weapon_world[0][3]),
        float(contact_weapon_world[1][3]),
        float(contact_weapon_world[2][3]),
    )
    intended_weapon_translation = tuple(float(value) for value in weapon_pose["translation"])
    weapon_pose_error_m = _distance(derived_weapon_translation, intended_weapon_translation)

    deform = deformation_evidence(body, weights, bind, posed)
    packet = {
        "schema": SCHEMA,
        "pose_id": "full_rig_cross_chest_low_ready_v0.2",
        "base_rig_schema": rig_evidence["schema"],
        "joint_count": len(bind.joints),
        "character_hand_sockets": {
            side: {
                "joint": indices[f"{side}_hand"],
                "name": hand_sockets[side].name,
                "position": list(hand_sockets[side].position),
                "rotation": list(hand_sockets[side].rotation),
            }
            for side in ("right", "left")
        },
        "weapon": {
            "asset": rifle.name,
            "scale": list(weapon_pose["scale"]),
            "intended_translation": list(intended_weapon_translation),
            "derived_translation": list(derived_weapon_translation),
            "translation_error_m": weapon_pose_error_m,
            "rotation": list(weapon_pose["rotation"]),
            "primary_socket": list(rifle.sockets["primary_grip"].position),
            "support_socket": list(rifle.sockets["support_grip"].position),
        },
        "pose": pose_rows,
        "contact": contact,
        "hand_geometry": hand_geometry,
        "deformation": deform,
        "truth": {
            "single_full_body_motion_truth": True,
            "arm_only_rig_required": False,
            "contact_only_bones_added": False,
            "character_side_hand_sockets_used": True,
            "canonical_body_mutated": False,
            "rifle_scaled_to_fake_contact": False,
            "production_rig_claim": False,
            "production_skinning_claim": False,
            "automatic_runtime_ik_claim": False,
            "notes": [
                "The 23-joint body-derived rig remains unchanged and owns deformation. Palm contact is represented by explicit local character-side sockets on the anatomical hand/wrist joints.",
                "Primary hand socket defines weapon placement; support hand socket is independently measured using the generic attachment v0.2 evidence path.",
                "Exact socket contact does not guarantee final hand mesh wrap. Posed hand centroid-to-socket error is recorded separately as a skinning/hand-quality repair signal.",
            ],
        },
    }
    return posed_mesh, packet


if __name__ == "__main__":
    import json
    mesh, packet = build_hm08_full_rifle_pose()
    print(json.dumps({"vertices": len(mesh.vertices), "faces": len(mesh.faces), **packet}, indent=2))
