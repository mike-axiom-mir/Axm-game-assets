#!/usr/bin/env python3
"""AXM native attachment sockets and two-point contact evidence v0.2.

The original joint-origin attachment API remains available. v0.2 adds an
explicit character-side hand-socket path so anatomical wrist/hand joints do not
have to be moved to the palm contact point just to satisfy a weapon grip.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import acos, degrees, sqrt
from typing import Sequence

from native_animation import AnimationClip, pose_skeleton
from native_geometry import Vec3
from native_skin import Mat4, Quat, Skeleton, global_joint_matrices, inverse4, matmul, transform_point, trs_matrix


@dataclass(frozen=True, slots=True)
class Socket:
    name: str
    position: Vec3 = (0.0, 0.0, 0.0)
    rotation: Quat = (0.0, 0.0, 0.0, 1.0)


@dataclass(frozen=True, slots=True)
class TwoHandAttachment:
    primary_joint: int
    support_joint: int
    primary_socket: Socket
    support_socket: Socket


@dataclass(frozen=True, slots=True)
class TwoHandSocketAttachment:
    """Two-hand attachment with explicit character and weapon contact sockets.

    ``primary_hand_socket`` and ``support_hand_socket`` are local to the
    corresponding character joints. ``primary_weapon_socket`` and
    ``support_weapon_socket`` are local to the weapon. The primary hand contact
    defines weapon world placement; support hand contact is measured
    independently and never silently repaired.
    """

    primary_joint: int
    support_joint: int
    primary_hand_socket: Socket
    support_hand_socket: Socket
    primary_weapon_socket: Socket
    support_weapon_socket: Socket


def _distance(a: Vec3, b: Vec3) -> float:
    return sqrt(sum((a[axis] - b[axis]) ** 2 for axis in range(3)))


def _normalize(value: Vec3) -> Vec3:
    length = sqrt(sum(component * component for component in value))
    if length <= 1e-12:
        return (0.0, 0.0, 1.0)
    return tuple(component / length for component in value)  # type: ignore[return-value]


def transform_direction(matrix: Mat4, direction: Vec3) -> Vec3:
    x, y, z = direction
    result = (
        matrix[0][0] * x + matrix[0][1] * y + matrix[0][2] * z,
        matrix[1][0] * x + matrix[1][1] * y + matrix[1][2] * z,
        matrix[2][0] * x + matrix[2][1] * y + matrix[2][2] * z,
    )
    return _normalize(result)


def orientation_error_degrees(a: Mat4, b: Mat4) -> float:
    errors = []
    for axis in ((0.0, 0.0, 1.0), (0.0, 1.0, 0.0)):
        av = transform_direction(a, axis)
        bv = transform_direction(b, axis)
        dot = max(-1.0, min(1.0, sum(x * y for x, y in zip(av, bv))))
        errors.append(degrees(acos(dot)))
    return max(errors)


def socket_matrix(socket: Socket) -> Mat4:
    return trs_matrix(socket.position, socket.rotation, (1.0, 1.0, 1.0))


def weapon_world_from_primary(primary_joint_world: Mat4, primary_socket: Socket) -> Mat4:
    return matmul(primary_joint_world, inverse4(socket_matrix(primary_socket)))


def contact_evidence(pose: Skeleton, attachment: TwoHandAttachment) -> dict[str, object]:
    if attachment.primary_joint == attachment.support_joint:
        raise ValueError("primary and support joints must differ")
    if attachment.primary_joint < 0 or attachment.primary_joint >= len(pose.joints):
        raise ValueError("primary joint outside skeleton")
    if attachment.support_joint < 0 or attachment.support_joint >= len(pose.joints):
        raise ValueError("support joint outside skeleton")
    globals_ = global_joint_matrices(pose)
    primary_world = globals_[attachment.primary_joint]
    support_world = globals_[attachment.support_joint]
    weapon_world = weapon_world_from_primary(primary_world, attachment.primary_socket)
    primary_target_world = matmul(weapon_world, socket_matrix(attachment.primary_socket))
    support_target_world = matmul(weapon_world, socket_matrix(attachment.support_socket))
    primary_position = transform_point(primary_world, (0.0, 0.0, 0.0))
    support_position = transform_point(support_world, (0.0, 0.0, 0.0))
    primary_target_position = transform_point(primary_target_world, (0.0, 0.0, 0.0))
    support_target_position = transform_point(support_target_world, (0.0, 0.0, 0.0))
    return {
        "primary_position_error": _distance(primary_position, primary_target_position),
        "primary_orientation_error_deg": orientation_error_degrees(primary_world, primary_target_world),
        "support_position_error": _distance(support_position, support_target_position),
        "support_orientation_error_deg": orientation_error_degrees(support_world, support_target_world),
        "weapon_world": [list(row) for row in weapon_world],
        "support_target_world_position": list(support_target_position),
    }


def socket_contact_evidence(pose: Skeleton, attachment: TwoHandSocketAttachment) -> dict[str, object]:
    if attachment.primary_joint == attachment.support_joint:
        raise ValueError("primary and support joints must differ")
    if attachment.primary_joint < 0 or attachment.primary_joint >= len(pose.joints):
        raise ValueError("primary joint outside skeleton")
    if attachment.support_joint < 0 or attachment.support_joint >= len(pose.joints):
        raise ValueError("support joint outside skeleton")

    globals_ = global_joint_matrices(pose)
    primary_joint_world = globals_[attachment.primary_joint]
    support_joint_world = globals_[attachment.support_joint]
    primary_hand_world = matmul(primary_joint_world, socket_matrix(attachment.primary_hand_socket))
    support_hand_world = matmul(support_joint_world, socket_matrix(attachment.support_hand_socket))
    weapon_world = matmul(primary_hand_world, inverse4(socket_matrix(attachment.primary_weapon_socket)))
    primary_weapon_world = matmul(weapon_world, socket_matrix(attachment.primary_weapon_socket))
    support_weapon_world = matmul(weapon_world, socket_matrix(attachment.support_weapon_socket))

    primary_hand_position = transform_point(primary_hand_world, (0.0, 0.0, 0.0))
    support_hand_position = transform_point(support_hand_world, (0.0, 0.0, 0.0))
    primary_weapon_position = transform_point(primary_weapon_world, (0.0, 0.0, 0.0))
    support_weapon_position = transform_point(support_weapon_world, (0.0, 0.0, 0.0))
    return {
        "primary_position_error": _distance(primary_hand_position, primary_weapon_position),
        "primary_orientation_error_deg": orientation_error_degrees(primary_hand_world, primary_weapon_world),
        "support_position_error": _distance(support_hand_position, support_weapon_position),
        "support_orientation_error_deg": orientation_error_degrees(support_hand_world, support_weapon_world),
        "weapon_world": [list(row) for row in weapon_world],
        "primary_hand_contact_world_position": list(primary_hand_position),
        "support_hand_contact_world_position": list(support_hand_position),
        "primary_weapon_target_world_position": list(primary_weapon_position),
        "support_weapon_target_world_position": list(support_weapon_position),
        "truth": "Character hand sockets, not wrist joint origins, define physical contact. Primary hand contact defines weapon placement; support contact is independently measured and no IK repair is silently applied.",
    }


def sample_two_hand_contact(
    bind_skeleton: Skeleton,
    clip: AnimationClip,
    attachment: TwoHandAttachment,
    sample_times: Sequence[float],
) -> dict[str, object]:
    if not sample_times:
        raise ValueError("two-hand contact proof needs sample times")
    samples = []
    for time in sample_times:
        pose = pose_skeleton(bind_skeleton, clip, float(time))
        evidence = contact_evidence(pose, attachment)
        samples.append({"time": float(time), **evidence})
    return {
        "samples": samples,
        "max_primary_position_error": max(sample["primary_position_error"] for sample in samples),
        "max_primary_orientation_error_deg": max(sample["primary_orientation_error_deg"] for sample in samples),
        "max_support_position_error": max(sample["support_position_error"] for sample in samples),
        "max_support_orientation_error_deg": max(sample["support_orientation_error_deg"] for sample in samples),
        "truth": "Primary socket defines weapon attachment. Support hand is independently measured against its socket; no IK repair is silently applied.",
    }


def sample_two_hand_socket_contact(
    bind_skeleton: Skeleton,
    clip: AnimationClip,
    attachment: TwoHandSocketAttachment,
    sample_times: Sequence[float],
) -> dict[str, object]:
    if not sample_times:
        raise ValueError("two-hand socket contact proof needs sample times")
    samples = []
    for time in sample_times:
        pose = pose_skeleton(bind_skeleton, clip, float(time))
        evidence = socket_contact_evidence(pose, attachment)
        samples.append({"time": float(time), **evidence})
    return {
        "samples": samples,
        "max_primary_position_error": max(sample["primary_position_error"] for sample in samples),
        "max_primary_orientation_error_deg": max(sample["primary_orientation_error_deg"] for sample in samples),
        "max_support_position_error": max(sample["support_position_error"] for sample in samples),
        "max_support_orientation_error_deg": max(sample["support_orientation_error_deg"] for sample in samples),
        "truth": "Character-side hand sockets remain explicit across animation sampling. Primary hand contact defines weapon placement; support contact is independently measured with no silent IK repair.",
    }
