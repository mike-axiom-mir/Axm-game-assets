#!/usr/bin/env python3
"""Deterministic two-arm rifle-contact pose for the pinned hm08 Sentinel body.

This is the first real bridge between the complete human substrate and Forge's
existing two-hand attachment evidence. It does not teleport hand joints or
scale the rifle to fit an A-pose. Instead it:
- derives shoulder/hand landmarks from the canonical full body,
- builds fixed-length shoulder/elbow/hand chains,
- solves a bounded two-bone cross-chest contact pose,
- skins only the arm regions with deterministic geometric proposal weights,
- measures the result against the real Sentinel rifle grip sockets.

The skinning is a proposal-quality static contact proof, not production rigging.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import acos, cos, isfinite, sin, sqrt
from typing import Sequence

from native_attachment import TwoHandAttachment, contact_evidence
from native_geometry import Mesh, Vec3, bounds
from native_hm08_extremity_gear import _load_identity_body
from native_skin import (
    Joint,
    Quat,
    Skeleton,
    SkinWeights,
    global_joint_matrices,
    normalize_quaternion,
    normalize_weights,
    skin_vertices,
    transform_point,
    validate_skeleton,
    validate_skin_weights,
)
from native_weapon import sentinel_rifle, validate_weapon

SCHEMA = "axm.game-assets.hm08-rifle-contact-pose.v0.1"


@dataclass(frozen=True, slots=True)
class ArmChain:
    side: str
    shoulder: Vec3
    elbow: Vec3
    hand: Vec3
    upper_length_m: float
    forearm_hand_length_m: float
    hand_vertex_indices: tuple[int, ...]


def _add(a: Vec3, b: Vec3) -> Vec3:
    return a[0]+b[0], a[1]+b[1], a[2]+b[2]


def _sub(a: Vec3, b: Vec3) -> Vec3:
    return a[0]-b[0], a[1]-b[1], a[2]-b[2]


def _mul(a: Vec3, value: float) -> Vec3:
    return a[0]*value, a[1]*value, a[2]*value


def _dot(a: Sequence[float], b: Sequence[float]) -> float:
    return sum(float(x)*float(y) for x, y in zip(a, b))


def _cross(a: Vec3, b: Vec3) -> Vec3:
    return (
        a[1]*b[2]-a[2]*b[1],
        a[2]*b[0]-a[0]*b[2],
        a[0]*b[1]-a[1]*b[0],
    )


def _length(a: Sequence[float]) -> float:
    return sqrt(sum(float(value)*float(value) for value in a))


def _normalize(a: Vec3) -> Vec3:
    length = _length(a)
    if length <= 1e-12:
        raise ValueError("cannot normalize zero vector")
    return a[0]/length, a[1]/length, a[2]/length


def _distance(a: Vec3, b: Vec3) -> float:
    return _length(_sub(a, b))


def _centroid(mesh: Mesh, indices: Sequence[int]) -> Vec3:
    if not indices:
        raise ValueError("centroid requires vertices")
    count = float(len(indices))
    return tuple(sum(mesh.vertices[index][axis] for index in indices)/count for axis in range(3))  # type: ignore[return-value]


def _quat_mul(a: Quat, b: Quat) -> Quat:
    ax, ay, az, aw = a
    bx, by, bz, bw = b
    return normalize_quaternion((
        aw*bx + ax*bw + ay*bz - az*by,
        aw*by - ax*bz + ay*bw + az*bx,
        aw*bz + ax*by - ay*bx + az*bw,
        aw*bw - ax*bx - ay*by - az*bz,
    ))


def _quat_conjugate(q: Quat) -> Quat:
    return -q[0], -q[1], -q[2], q[3]


def _quat_rotate(q: Quat, vector: Vec3) -> Vec3:
    x, y, z = vector
    qx, qy, qz, qw = q
    # Quaternion-vector rotation expanded directly to avoid treating a vector
    # quaternion as a unit quaternion in _quat_mul.
    tx = 2.0 * (qy*z - qz*y)
    ty = 2.0 * (qz*x - qx*z)
    tz = 2.0 * (qx*y - qy*x)
    return (
        x + qw*tx + (qy*tz - qz*ty),
        y + qw*ty + (qz*tx - qx*tz),
        z + qw*tz + (qx*ty - qy*tx),
    )


def _quat_from_to(source: Vec3, target: Vec3) -> Quat:
    a = _normalize(source)
    b = _normalize(target)
    dot = max(-1.0, min(1.0, _dot(a, b)))
    if dot >= 1.0 - 1e-10:
        return (0.0, 0.0, 0.0, 1.0)
    if dot <= -1.0 + 1e-8:
        axis = _cross(a, (1.0, 0.0, 0.0))
        if _length(axis) <= 1e-8:
            axis = _cross(a, (0.0, 1.0, 0.0))
        axis = _normalize(axis)
        return axis[0], axis[1], axis[2], 0.0
    axis = _cross(a, b)
    return normalize_quaternion((axis[0], axis[1], axis[2], 1.0 + dot))


def _solve_elbow(
    shoulder: Vec3,
    hand: Vec3,
    upper_length: float,
    forearm_length: float,
    hint: Vec3,
) -> Vec3:
    delta = _sub(hand, shoulder)
    distance = _length(delta)
    if distance <= 1e-9:
        raise ValueError("hand target coincides with shoulder")
    if distance > upper_length + forearm_length + 1e-9:
        raise ValueError(f"hand target outside arm reach: {distance:.6f} > {upper_length+forearm_length:.6f}")
    if distance < abs(upper_length - forearm_length) - 1e-9:
        raise ValueError("hand target is inside two-bone minimum reach")
    direction = _mul(delta, 1.0/distance)
    along = (upper_length*upper_length - forearm_length*forearm_length + distance*distance) / (2.0*distance)
    height_sq = max(0.0, upper_length*upper_length - along*along)
    circle_center = _add(shoulder, _mul(direction, along))
    hint_delta = _sub(hint, circle_center)
    projected = _sub(hint_delta, _mul(direction, _dot(hint_delta, direction)))
    if _length(projected) <= 1e-9:
        projected = _cross(direction, (0.0, 1.0, 0.0))
        if _length(projected) <= 1e-9:
            projected = _cross(direction, (0.0, 0.0, 1.0))
    perpendicular = _normalize(projected)
    return _add(circle_center, _mul(perpendicular, sqrt(height_sq)))


def derive_hm08_arm_chains(body_m: Mesh) -> dict[str, ArmChain]:
    lo, hi = bounds(body_m)
    height = hi[1] - lo[1]
    half_width = max(abs(lo[0]), abs(hi[0]), 1e-9)
    if not (1.4 <= height <= 2.2):
        raise ValueError(f"hm08 contact pose expects human-scale body, got {height}")

    # These lengths intentionally describe shoulder->elbow and elbow->hand
    # center, not shoulder->fingertip. They are derived from body height and the
    # resulting bind elbow must still land on the measured hand centroid.
    upper_length = height * 0.125
    forearm_hand_length = height * 0.115
    chains: dict[str, ArmChain] = {}
    for side, sign in (("right", 1.0), ("left", -1.0)):
        lateral = [sign * point[0] for point in body_m.vertices]
        shoulder_indices = [
            index for index, point in enumerate(body_m.vertices)
            if half_width*0.48 <= lateral[index] <= half_width*0.68
            and lo[1] + height*0.70 <= point[1] <= lo[1] + height*0.82
            and point[2] <= lo[2] + (hi[2]-lo[2])*0.62
        ]
        hand_indices = [
            index for index, point in enumerate(body_m.vertices)
            if lateral[index] >= half_width*0.84
            and lo[1] + height*0.55 <= point[1] <= lo[1] + height*0.67
        ]
        if len(shoulder_indices) < 30 or len(hand_indices) < 300:
            raise ValueError(f"{side} arm landmark selection too sparse: shoulder={len(shoulder_indices)} hand={len(hand_indices)}")
        shoulder = _centroid(body_m, shoulder_indices)
        hand = _centroid(body_m, hand_indices)
        line_hint = _add(shoulder, _mul(_sub(hand, shoulder), 0.52))
        hint = _add(line_hint, (-sign*0.020, -0.040, -0.020))
        elbow = _solve_elbow(shoulder, hand, upper_length, forearm_hand_length, hint)
        chains[side] = ArmChain(
            side, shoulder, elbow, hand, upper_length, forearm_hand_length, tuple(hand_indices)
        )
    return chains


def build_bind_skeleton(chains: dict[str, ArmChain]) -> tuple[Skeleton, dict[str, int]]:
    right = chains["right"]
    left = chains["left"]
    joints = [Joint("root")]
    index = {"root": 0}
    for side, chain in (("right", right), ("left", left)):
        shoulder_index = len(joints)
        joints.append(Joint(f"{side}_shoulder", parent=0, translation=chain.shoulder))
        elbow_index = len(joints)
        joints.append(Joint(f"{side}_elbow", parent=shoulder_index, translation=_sub(chain.elbow, chain.shoulder)))
        hand_index = len(joints)
        joints.append(Joint(f"{side}_hand", parent=elbow_index, translation=_sub(chain.hand, chain.elbow)))
        index[f"{side}_shoulder"] = shoulder_index
        index[f"{side}_elbow"] = elbow_index
        index[f"{side}_hand"] = hand_index
    skeleton = Skeleton(joints)
    report = validate_skeleton(skeleton)
    if report["status"] != "pass":
        raise ValueError(f"derived hm08 bind skeleton invalid: {report}")
    return skeleton, index


def _world_weapon_pose(body_m: Mesh, chains: dict[str, ArmChain], rifle) -> dict[str, object]:
    right = chains["right"]
    left = chains["left"]
    lo, hi = bounds(body_m)
    height = hi[1] - lo[1]
    chest_points = [
        point for point in body_m.vertices
        if lo[1] + height*0.66 <= point[1] <= lo[1] + height*0.79
        and abs(point[0]) <= max(abs(lo[0]), abs(hi[0]))*0.45
    ]
    if not chest_points:
        raise ValueError("cannot derive chest front for rifle pose")
    chest_front_z = max(point[2] for point in chest_points)

    # Cross-chest low-ready proof. Rifle local +X points mostly toward the
    # character's left side with a small forward component. This keeps the
    # stock near the right shoulder and both real grip sockets inside arm reach.
    direction = _normalize((-0.989, 0.0, 0.148))
    weapon_rotation = _quat_from_to((1.0, 0.0, 0.0), direction)
    shoulder_y = (right.shoulder[1] + left.shoulder[1]) * 0.5
    primary_hand_target = (0.0, shoulder_y - height*0.060, chest_front_z + 0.040)

    primary_socket = rifle.sockets["primary_grip"]
    support_socket = rifle.sockets["support_grip"]
    primary_offset = _quat_rotate(weapon_rotation, primary_socket.position)
    weapon_translation = _sub(primary_hand_target, primary_offset)
    support_target = _add(weapon_translation, _quat_rotate(weapon_rotation, support_socket.position))
    primary_target = _add(weapon_translation, primary_offset)

    for side, shoulder, target, chain in (
        ("right", right.shoulder, primary_target, right),
        ("left", left.shoulder, support_target, left),
    ):
        reach = _distance(shoulder, target)
        maximum = chain.upper_length_m + chain.forearm_hand_length_m
        if reach > maximum + 1e-9:
            raise ValueError(f"{side} rifle target outside arm reach: {reach} > {maximum}")

    return {
        "translation": weapon_translation,
        "rotation": weapon_rotation,
        "forward": direction,
        "scale": (1.0, 1.0, 1.0),
        "primary_target": primary_target,
        "support_target": support_target,
        "chest_front_z": chest_front_z,
    }


def _pose_arm(
    chain: ArmChain,
    target: Vec3,
    desired_hand_world_rotation: Quat,
    *,
    sign: float,
) -> tuple[Vec3, Quat, Quat, Quat]:
    hint = _add(_add(chain.shoulder, _mul(_sub(target, chain.shoulder), 0.50)), (sign*0.010, -0.040, -0.020))
    elbow = _solve_elbow(
        chain.shoulder, target, chain.upper_length_m, chain.forearm_hand_length_m, hint
    )
    bind_upper = _sub(chain.elbow, chain.shoulder)
    posed_upper = _sub(elbow, chain.shoulder)
    shoulder_rotation = _quat_from_to(bind_upper, posed_upper)

    bind_forearm = _sub(chain.hand, chain.elbow)
    posed_forearm_world = _sub(target, elbow)
    posed_forearm_local = _quat_rotate(_quat_conjugate(shoulder_rotation), posed_forearm_world)
    elbow_rotation = _quat_from_to(bind_forearm, posed_forearm_local)
    parent_global = _quat_mul(shoulder_rotation, elbow_rotation)
    hand_rotation = _quat_mul(_quat_conjugate(parent_global), desired_hand_world_rotation)
    return elbow, shoulder_rotation, elbow_rotation, hand_rotation


def build_contact_pose_skeleton(
    bind_skeleton: Skeleton,
    indices: dict[str, int],
    chains: dict[str, ArmChain],
    weapon_pose: dict[str, object],
    rifle,
) -> tuple[Skeleton, dict[str, object]]:
    joints = list(bind_skeleton.joints)
    weapon_rotation = weapon_pose["rotation"]
    assert isinstance(weapon_rotation, tuple)

    pose_rows: dict[str, object] = {}
    for side, sign, target_key, socket_key in (
        ("right", 1.0, "primary_target", "primary_grip"),
        ("left", -1.0, "support_target", "support_grip"),
    ):
        chain = chains[side]
        target = weapon_pose[target_key]
        assert isinstance(target, tuple)
        socket = rifle.sockets[socket_key]
        desired_hand_rotation = _quat_mul(weapon_rotation, socket.rotation)
        elbow, shoulder_rotation, elbow_rotation, hand_rotation = _pose_arm(
            chain, target, desired_hand_rotation, sign=sign
        )
        shoulder_index = indices[f"{side}_shoulder"]
        elbow_index = indices[f"{side}_elbow"]
        hand_index = indices[f"{side}_hand"]
        shoulder_joint = joints[shoulder_index]
        elbow_joint = joints[elbow_index]
        hand_joint = joints[hand_index]
        joints[shoulder_index] = Joint(shoulder_joint.name, shoulder_joint.parent, shoulder_joint.translation, shoulder_rotation)
        joints[elbow_index] = Joint(elbow_joint.name, elbow_joint.parent, elbow_joint.translation, elbow_rotation)
        joints[hand_index] = Joint(hand_joint.name, hand_joint.parent, hand_joint.translation, hand_rotation)
        pose_rows[side] = {
            "target": list(target),
            "elbow": list(elbow),
            "upper_length_m": chain.upper_length_m,
            "forearm_hand_length_m": chain.forearm_hand_length_m,
            "shoulder_rotation": list(shoulder_rotation),
            "elbow_rotation": list(elbow_rotation),
            "hand_rotation": list(hand_rotation),
        }

    posed = Skeleton(joints)
    report = validate_skeleton(posed)
    if report["status"] != "pass":
        raise ValueError(f"posed hm08 contact skeleton invalid: {report}")
    return posed, pose_rows


def build_arm_skin_weights(
    body_m: Mesh,
    chains: dict[str, ArmChain],
    indices: dict[str, int],
) -> tuple[SkinWeights, dict[str, object]]:
    lo, hi = bounds(body_m)
    height = hi[1] - lo[1]
    half_width = max(abs(lo[0]), abs(hi[0]), 1e-9)
    hand_sets = {side: set(chain.hand_vertex_indices) for side, chain in chains.items()}
    raw_joints = []
    raw_weights = []
    arm_vertices = {"right": 0, "left": 0}
    rigid_hand_vertices = {"right": 0, "left": 0}

    for vertex_index, point in enumerate(body_m.vertices):
        assigned = False
        for side, sign in (("right", 1.0), ("left", -1.0)):
            chain = chains[side]
            lateral = sign * point[0]
            if (
                lateral >= abs(chain.shoulder[0])*0.82
                and chain.hand[1] - height*0.070 <= point[1] <= chain.shoulder[1] + height*0.075
            ):
                shoulder_joint = indices[f"{side}_shoulder"]
                elbow_joint = indices[f"{side}_elbow"]
                hand_joint = indices[f"{side}_hand"]
                arm_vertices[side] += 1
                if vertex_index in hand_sets[side]:
                    raw_joints.append((hand_joint, 0, 0, 0))
                    raw_weights.append((1.0, 0.0, 0.0, 0.0))
                    rigid_hand_vertices[side] += 1
                    assigned = True
                    break

                axis = _sub(chain.hand, chain.shoulder)
                axis_len_sq = max(_dot(axis, axis), 1e-12)
                t = max(0.0, min(1.0, _dot(_sub(point, chain.shoulder), axis)/axis_len_sq))
                if t < 0.12:
                    root = 1.0 - t/0.12
                    shoulder = 1.0 - root
                    row = ((0, shoulder_joint, 0, 0), (root, shoulder, 0.0, 0.0))
                elif t < 0.52:
                    elbow = (t - 0.12) / 0.40
                    row = ((shoulder_joint, elbow_joint, 0, 0), (1.0-elbow, elbow, 0.0, 0.0))
                elif t < 0.82:
                    hand = (t - 0.52) / 0.30
                    row = ((elbow_joint, hand_joint, 0, 0), (1.0-hand, hand, 0.0, 0.0))
                else:
                    row = ((hand_joint, 0, 0, 0), (1.0, 0.0, 0.0, 0.0))
                raw_joints.append(row[0])
                raw_weights.append(row[1])
                assigned = True
                break
        if not assigned:
            raw_joints.append((0, 0, 0, 0))
            raw_weights.append((1.0, 0.0, 0.0, 0.0))

    weights = normalize_weights(SkinWeights(raw_joints, raw_weights))
    report = validate_skin_weights(weights, vertex_count=len(body_m.vertices), joint_count=len(indices))
    if report["status"] != "pass":
        raise ValueError(f"hm08 contact proposal skin invalid: {report}")
    return weights, {
        "arm_vertices": arm_vertices,
        "rigid_hand_vertices": rigid_hand_vertices,
        "root_only_vertices": len(body_m.vertices) - arm_vertices["right"] - arm_vertices["left"],
        "validation": report,
    }


def build_hm08_rifle_contact_pose(body_m: Mesh) -> tuple[Mesh, dict[str, object]]:
    rifle = sentinel_rifle()
    weapon_report = validate_weapon(rifle)
    if weapon_report["status"] != "pass":
        raise ValueError(f"rifle invalid before contact pose: {weapon_report}")
    chains = derive_hm08_arm_chains(body_m)
    bind, indices = build_bind_skeleton(chains)
    weapon_pose = _world_weapon_pose(body_m, chains, rifle)
    posed, pose_rows = build_contact_pose_skeleton(bind, indices, chains, weapon_pose, rifle)
    weights, weight_evidence = build_arm_skin_weights(body_m, chains, indices)
    posed_vertices = skin_vertices(body_m, weights, bind, posed)
    posed_mesh = Mesh("sentinel_hm08_rifle_contact_pose_v0_1", posed_vertices, list(body_m.faces))

    attachment = TwoHandAttachment(
        primary_joint=indices["right_hand"],
        support_joint=indices["left_hand"],
        primary_socket=rifle.sockets["primary_grip"],
        support_socket=rifle.sockets["support_grip"],
    )
    contact = contact_evidence(posed, attachment)
    globals_ = global_joint_matrices(posed)
    right_hand_world = transform_point(globals_[indices["right_hand"]], (0.0, 0.0, 0.0))
    left_hand_world = transform_point(globals_[indices["left_hand"]], (0.0, 0.0, 0.0))

    hand_centroid_errors = {}
    for side, target in (("right", right_hand_world), ("left", left_hand_world)):
        centroid = _centroid(posed_mesh, chains[side].hand_vertex_indices)
        hand_centroid_errors[side] = {
            "centroid": list(centroid),
            "joint": list(target),
            "error_m": _distance(centroid, target),
        }

    # Root-only vertices must not move at all. This is the strongest truth gate
    # for this proposal layer: only arm-region weights may alter the body.
    non_arm_max = 0.0
    moved_vertices = 0
    for index, (before, after) in enumerate(zip(body_m.vertices, posed_mesh.vertices)):
        distance = _distance(before, after)
        if distance > 1e-12:
            moved_vertices += 1
        if weights.weights[index][0] >= 1.0 - 1e-12 and weights.joints[index][0] == 0:
            non_arm_max = max(non_arm_max, distance)

    bone_lengths = {}
    for side in ("right", "left"):
        shoulder = transform_point(globals_[indices[f"{side}_shoulder"]], (0.0,0.0,0.0))
        elbow = transform_point(globals_[indices[f"{side}_elbow"]], (0.0,0.0,0.0))
        hand = transform_point(globals_[indices[f"{side}_hand"]], (0.0,0.0,0.0))
        bone_lengths[side] = {
            "upper_bind_m": chains[side].upper_length_m,
            "upper_posed_m": _distance(shoulder, elbow),
            "forearm_hand_bind_m": chains[side].forearm_hand_length_m,
            "forearm_hand_posed_m": _distance(elbow, hand),
        }

    socket_separation = _distance(rifle.sockets["primary_grip"].position, rifle.sockets["support_grip"].position)
    a_pose_hand_separation = _distance(chains["right"].hand, chains["left"].hand)
    packet: dict[str, object] = {
        "schema": SCHEMA,
        "pose_id": "cross_chest_low_ready_v0.1",
        "weapon": {
            "asset": rifle.name,
            "scale": list(weapon_pose["scale"]),
            "translation": list(weapon_pose["translation"]),
            "rotation": list(weapon_pose["rotation"]),
            "forward": list(weapon_pose["forward"]),
            "primary_socket": list(rifle.sockets["primary_grip"].position),
            "support_socket": list(rifle.sockets["support_grip"].position),
            "grip_socket_separation_m": socket_separation,
        },
        "a_pose_hand_separation_m": a_pose_hand_separation,
        "chains": {
            side: {
                "shoulder": list(chain.shoulder),
                "bind_elbow": list(chain.elbow),
                "bind_hand": list(chain.hand),
                "upper_length_m": chain.upper_length_m,
                "forearm_hand_length_m": chain.forearm_hand_length_m,
                "hand_vertices": len(chain.hand_vertex_indices),
            }
            for side, chain in chains.items()
        },
        "pose": pose_rows,
        "contact": contact,
        "hand_centroid_contact": hand_centroid_errors,
        "bone_lengths": bone_lengths,
        "skin_proposal": weight_evidence,
        "moved_vertices": moved_vertices,
        "non_arm_max_displacement_m": non_arm_max,
        "truth": {
            "rifle_scaled_to_fake_contact": False,
            "hand_teleport_claim": False,
            "two_bone_lengths_preserved": True,
            "canonical_body_mutated": False,
            "production_rig_claim": False,
            "production_skinning_claim": False,
            "automatic_ik_runtime_claim": False,
            "notes": [
                "The original A-pose hands are much farther apart than the rifle's real grip sockets, so rigid weapon placement alone cannot prove two-hand contact.",
                "The pose is solved through fixed-length shoulder/elbow/hand chains and the existing attachment evidence; the rifle remains at scale 1.0.",
                "Geometric arm weights are a reversible proposal layer used to produce a static contact mesh. Production deformation still requires an authored humanoid skeleton, weight refinement and pose/animation evidence.",
                "Rigid armor is intentionally excluded from the first contact visual proof because the current armor layer does not yet deform with these arm chains."
            ],
        },
    }
    return posed_mesh, packet


def build_preferred_hm08_rifle_contact_pose():
    body_m, _body_uv, _state = _load_identity_body()
    return build_hm08_rifle_contact_pose(body_m)


if __name__ == "__main__":
    import json
    mesh, packet = build_preferred_hm08_rifle_contact_pose()
    print(json.dumps({"vertices":len(mesh.vertices),"faces":len(mesh.faces),**packet}, indent=2))
