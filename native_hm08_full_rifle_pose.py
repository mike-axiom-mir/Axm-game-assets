#!/usr/bin/env python3
"""Two-hand Sentinel rifle pose on the real full-body humanoid rig.

This bridge replaces the temporary arm-only rig as contact authority while
preserving that earlier proof as evidence. The 23-joint body-derived skeleton is
augmented with two zero-weight palm contact markers. Shoulder/elbow/wrist bones
remain the deformation pivots; palm markers are attachment evidence only.
"""
from __future__ import annotations

from dataclasses import replace
from math import sqrt

from native_attachment import TwoHandAttachment, contact_evidence
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
from native_skin import Joint, Skeleton, global_joint_matrices, skin_vertices, transform_point, validate_skeleton
from native_weapon import sentinel_rifle, validate_weapon

SCHEMA = "axm.game-assets.hm08-full-rifle-pose.v0.1"


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


def _augment_grip_markers(
    bind: Skeleton,
    name_to_index: dict[str, int],
    body: Mesh,
    landmarks: dict[str, tuple[float, float, float]],
) -> tuple[Skeleton, dict[str, int], dict[str, tuple[float, float, float]], dict[str, tuple[int, ...]]]:
    joints = list(bind.joints)
    indices = dict(name_to_index)
    palms = {}
    hand_sets = {}
    for side in ("right", "left"):
        hand_sets[side] = _hand_indices(body, side=side)
        palm = _centroid(body, hand_sets[side])
        palms[side] = palm
        wrist = landmarks[f"{side}_hand"]
        hand_index = indices[f"{side}_hand"]
        marker_index = len(joints)
        joints.append(Joint(
            f"{side}_palm_contact",
            parent=hand_index,
            translation=_sub(palm, wrist),
        ))
        indices[f"{side}_palm_contact"] = marker_index
    augmented = Skeleton(joints)
    report = validate_skeleton(augmented)
    if report["status"] != "pass":
        raise ValueError(f"augmented full-body contact skeleton invalid: {report}")
    return augmented, indices, palms, hand_sets


def _contact_chains(
    body: Mesh,
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
    joints: list[Joint],
    indices: dict[str, int],
    landmarks: dict[str, tuple[float, float, float]],
    palms: dict[str, tuple[float, float, float]],
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
    desired_hand_world_rotation = _quat_mul(weapon_rotation, rifle.sockets[socket_key].rotation)

    wrist_bind = landmarks[f"{side}_hand"]
    palm_bind = palms[side]
    palm_offset_local = _sub(palm_bind, wrist_bind)
    rotated_palm_offset = _quat_rotate(desired_hand_world_rotation, palm_offset_local)
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
    hand_rotation = _quat_mul(_quat_conjugate(parent_global), desired_hand_world_rotation)

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
        "palm_offset_from_wrist_m": list(palm_offset_local),
        "shoulder_rotation": list(shoulder_rotation),
        "elbow_rotation": list(elbow_rotation),
        "hand_rotation": list(hand_rotation),
    }


def build_hm08_full_rifle_pose() -> tuple[Mesh, dict[str, object]]:
    body, bind, weights, _diagnostic, rig_evidence = build_preferred_hm08_humanoid_rig()
    landmarks = derive_hm08_rig_landmarks(body)
    base_indices = dict(rig_evidence["joint_indices"])
    augmented_bind, indices, palms, hand_sets = _augment_grip_markers(bind, base_indices, body, landmarks)
    chains = _contact_chains(body, landmarks, palms, hand_sets)

    rifle = sentinel_rifle()
    weapon_report = validate_weapon(rifle)
    if weapon_report["status"] != "pass":
        raise ValueError(f"rifle invalid before full-rig contact: {weapon_report}")
    weapon_pose = _world_weapon_pose(body, chains, rifle)

    joints = list(augmented_bind.joints)
    pose_rows = {
        "right": _solve_full_arm(
            joints, indices, landmarks, palms, chains, weapon_pose, rifle,
            side="right", sign=1.0, target_key="primary_target", socket_key="primary_grip",
        ),
        "left": _solve_full_arm(
            joints, indices, landmarks, palms, chains, weapon_pose, rifle,
            side="left", sign=-1.0, target_key="support_target", socket_key="support_grip",
        ),
    }
    posed = Skeleton(joints)
    posed_report = validate_skeleton(posed)
    if posed_report["status"] != "pass":
        raise ValueError(f"full-rig rifle pose invalid: {posed_report}")

    attachment = TwoHandAttachment(
        primary_joint=indices["right_palm_contact"],
        support_joint=indices["left_palm_contact"],
        primary_socket=rifle.sockets["primary_grip"],
        support_socket=rifle.sockets["support_grip"],
    )
    contact = contact_evidence(posed, attachment)
    posed_vertices = skin_vertices(body, weights, augmented_bind, posed)
    posed_mesh = Mesh("sentinel_hm08_full_rig_rifle_pose_v0_1", posed_vertices, list(body.faces))
    globals_ = global_joint_matrices(posed)

    hand_geometry = {}
    for side in ("right", "left"):
        marker = transform_point(globals_[indices[f"{side}_palm_contact"]], (0.0, 0.0, 0.0))
        centroid = _centroid(posed_mesh, hand_sets[side])
        hand_geometry[side] = {
            "contact_marker": list(marker),
            "posed_hand_centroid": list(centroid),
            "centroid_to_marker_error_m": _distance(centroid, marker),
            "hand_vertices": len(hand_sets[side]),
        }

    deform = deformation_evidence(body, weights, augmented_bind, posed)
    packet = {
        "schema": SCHEMA,
        "pose_id": "full_rig_cross_chest_low_ready_v0.1",
        "base_rig_schema": rig_evidence["schema"],
        "base_joint_count": len(bind.joints),
        "augmented_joint_count": len(augmented_bind.joints),
        "contact_markers": {
            "right": indices["right_palm_contact"],
            "left": indices["left_palm_contact"],
            "weight_influences": 0,
        },
        "weapon": {
            "asset": rifle.name,
            "scale": list(weapon_pose["scale"]),
            "translation": list(weapon_pose["translation"]),
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
            "canonical_body_mutated": False,
            "rifle_scaled_to_fake_contact": False,
            "production_rig_claim": False,
            "production_skinning_claim": False,
            "automatic_runtime_ik_claim": False,
            "notes": [
                "The full 23-joint body-derived rig remains the deformation authority; two zero-weight palm markers are appended only for exact attachment evidence.",
                "Shoulder/elbow/wrist pivots remain anatomical deformation pivots. Palm contact is represented as a child marker rather than moving the wrist joint into the grip.",
                "Exact marker/socket contact does not guarantee final hand mesh wrap; posed hand centroid error is recorded separately and remains a skin/hand-quality repair signal.",
            ],
        },
    }
    return posed_mesh, packet


if __name__ == "__main__":
    import json
    mesh, packet = build_hm08_full_rifle_pose()
    print(json.dumps({"vertices": len(mesh.vertices), "faces": len(mesh.faces), **packet}, indent=2))
