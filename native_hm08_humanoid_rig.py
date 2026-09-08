#!/usr/bin/env python3
"""Body-derived humanoid rig + four-weight skin for the pinned hm08 Sentinel body.

This is the first real full-body rig state for the Sentinel proving asset. Joint
pivots are inferred from deterministic surface regions on the canonical human
body rather than copied from a DCC rig. Torso pivots use front/back slice
midpoints so the rotation centers lie inside the body volume. Skin weights use
continuous anatomical gates and are normalized to four slots.

The result is an AXM-owned rig substrate. It is not yet a production autorigger:
corrective shapes, finger chains, twist bones, deformation-aware wearable
binding, and animation-quality judgments remain separate gates.
"""
from __future__ import annotations

import json
from dataclasses import replace
from math import cos, radians, sin, sqrt
from statistics import median

from native_geometry import Mesh, bounds
from native_hm08_undersuit import _load_identity_body
from native_skin import Joint, Skeleton, SkinWeights, normalize_weights, skin_vertices, validate_skeleton, validate_skin_weights

SCHEMA = "axm.game-assets.hm08-humanoid-rig.v0.1"


def _distance(a, b) -> float:
    return sqrt(sum((a[i] - b[i]) ** 2 for i in range(3)))


def _smoothstep(edge0: float, edge1: float, value: float) -> float:
    if edge1 <= edge0:
        return 0.0
    t = max(0.0, min(1.0, (value - edge0) / (edge1 - edge0)))
    return t * t * (3.0 - 2.0 * t)


def _median_point(points: list[tuple[float, float, float]], *, label: str) -> tuple[float, float, float]:
    if len(points) < 12:
        raise ValueError(f"rig landmark region {label} too small: {len(points)}")
    return tuple(float(median(point[axis] for point in points)) for axis in range(3))  # type: ignore[return-value]


def _region(
    body: Mesh,
    *,
    x_min: float,
    x_max: float,
    y_min: float,
    y_max: float,
    label: str,
) -> tuple[float, float, float]:
    rows = [point for point in body.vertices if x_min <= point[0] <= x_max and y_min <= point[1] <= y_max]
    return _median_point(rows, label=label)


def _centerline_z(body: Mesh, y: float, *, y_radius: float, x_radius: float) -> float:
    rows = [point[2] for point in body.vertices if abs(point[0]) <= x_radius and abs(point[1] - y) <= y_radius]
    if len(rows) < 8:
        raise ValueError(f"centerline sample too small at y={y:.6f}: {len(rows)}")
    # Mesh vertices live on the skin surface. The median can therefore land on
    # whichever side has denser topology. Front/back midpoint is the bounded
    # volumetric interpretation required for a rotation pivot.
    return (min(rows) + max(rows)) * 0.5


def derive_hm08_rig_landmarks(body: Mesh) -> dict[str, tuple[float, float, float]]:
    lo, hi = bounds(body)
    width = hi[0] - lo[0]
    height = hi[1] - lo[1]
    half_width = width * 0.5
    if not (1.45 <= height <= 2.15):
        raise ValueError(f"unexpected body height for humanoid rig: {height}")

    def yfrac(value: float) -> float:
        return lo[1] + height * value

    # Positive-X landmarks are measured from the actual current body. Negative-X
    # joints are mirrored only after those measurements exist.
    shoulder_r = _region(
        body,
        x_min=half_width * 0.24, x_max=half_width * 0.56,
        y_min=yfrac(0.75), y_max=yfrac(0.83), label="right_shoulder",
    )
    elbow_r = _region(
        body,
        x_min=half_width * 0.54, x_max=half_width * 0.80,
        y_min=yfrac(0.65), y_max=yfrac(0.72), label="right_elbow",
    )
    wrist_r = _region(
        body,
        x_min=half_width * 0.76, x_max=half_width * 0.96,
        y_min=yfrac(0.59), y_max=yfrac(0.66), label="right_wrist",
    )
    hand_r = _region(
        body,
        x_min=half_width * 0.80, x_max=half_width * 1.01,
        y_min=yfrac(0.55), y_max=yfrac(0.65), label="right_hand",
    )
    hip_r = _region(
        body,
        x_min=half_width * 0.10, x_max=half_width * 0.38,
        y_min=yfrac(0.44), y_max=yfrac(0.52), label="right_hip",
    )
    knee_r = _region(
        body,
        x_min=half_width * 0.14, x_max=half_width * 0.45,
        y_min=yfrac(0.28), y_max=yfrac(0.40), label="right_knee",
    )
    ankle_r = _region(
        body,
        x_min=half_width * 0.34, x_max=half_width * 0.56,
        y_min=yfrac(0.04), y_max=yfrac(0.12), label="right_ankle",
    )
    foot_r = _region(
        body,
        x_min=half_width * 0.34, x_max=half_width * 0.58,
        y_min=yfrac(0.00), y_max=yfrac(0.055), label="right_foot",
    )

    # Surface medians are regularized toward limb interior depth. X/Y remain
    # measured from the canonical body so proportions/stance continue to drive
    # the inferred rig rather than a fixed humanoid template.
    shoulder_r = (shoulder_r[0], shoulder_r[1], shoulder_r[2] * 0.55)
    elbow_r = (elbow_r[0], elbow_r[1], elbow_r[2] * 0.70)
    wrist_r = (wrist_r[0], wrist_r[1], wrist_r[2] * 0.92)
    hand_r = (hand_r[0], hand_r[1], hand_r[2] * 0.95)
    hip_r = (hip_r[0], hip_r[1], hip_r[2] * 0.55)
    knee_r = (knee_r[0], knee_r[1], knee_r[2] * 0.65)
    ankle_r = (ankle_r[0], ankle_r[1], ankle_r[2] * 0.55)
    foot_r = (foot_r[0], foot_r[1], foot_r[2])

    center_y = {
        "pelvis": yfrac(0.48),
        "spine_lower": yfrac(0.56),
        "spine_mid": yfrac(0.65),
        "chest": yfrac(0.75),
        "neck": yfrac(0.86),
        "head": yfrac(0.943),
    }
    center = {
        name: (0.0, y, _centerline_z(body, y, y_radius=height * 0.018, x_radius=width * 0.085))
        for name, y in center_y.items()
    }
    clavicle_r = (
        shoulder_r[0] * 0.43,
        center["chest"][1] * 0.35 + shoulder_r[1] * 0.65,
        center["chest"][2] * 0.60 + shoulder_r[2] * 0.40,
    )

    def mirror(point):
        return (-point[0], point[1], point[2])

    return {
        **center,
        "right_clavicle": clavicle_r,
        "right_upper_arm": shoulder_r,
        "right_forearm": elbow_r,
        "right_hand": wrist_r,
        "right_hand_tip": hand_r,
        "left_clavicle": mirror(clavicle_r),
        "left_upper_arm": mirror(shoulder_r),
        "left_forearm": mirror(elbow_r),
        "left_hand": mirror(wrist_r),
        "left_hand_tip": mirror(hand_r),
        "right_thigh": hip_r,
        "right_shin": knee_r,
        "right_foot": ankle_r,
        "right_toe": foot_r,
        "left_thigh": mirror(hip_r),
        "left_shin": mirror(knee_r),
        "left_foot": mirror(ankle_r),
        "left_toe": mirror(foot_r),
    }


def _joint_table(landmarks: dict[str, tuple[float, float, float]]):
    return [
        ("root", None, (0.0, 0.0, 0.0)),
        ("pelvis", "root", landmarks["pelvis"]),
        ("spine_lower", "pelvis", landmarks["spine_lower"]),
        ("spine_mid", "spine_lower", landmarks["spine_mid"]),
        ("chest", "spine_mid", landmarks["chest"]),
        ("neck", "chest", landmarks["neck"]),
        ("head", "neck", landmarks["head"]),
        ("left_clavicle", "chest", landmarks["left_clavicle"]),
        ("left_upper_arm", "left_clavicle", landmarks["left_upper_arm"]),
        ("left_forearm", "left_upper_arm", landmarks["left_forearm"]),
        ("left_hand", "left_forearm", landmarks["left_hand"]),
        ("right_clavicle", "chest", landmarks["right_clavicle"]),
        ("right_upper_arm", "right_clavicle", landmarks["right_upper_arm"]),
        ("right_forearm", "right_upper_arm", landmarks["right_forearm"]),
        ("right_hand", "right_forearm", landmarks["right_hand"]),
        ("left_thigh", "pelvis", landmarks["left_thigh"]),
        ("left_shin", "left_thigh", landmarks["left_shin"]),
        ("left_foot", "left_shin", landmarks["left_foot"]),
        ("left_toe", "left_foot", landmarks["left_toe"]),
        ("right_thigh", "pelvis", landmarks["right_thigh"]),
        ("right_shin", "right_thigh", landmarks["right_shin"]),
        ("right_foot", "right_shin", landmarks["right_foot"]),
        ("right_toe", "right_foot", landmarks["right_toe"]),
    ]


def build_hm08_humanoid_skeleton(body: Mesh) -> tuple[Skeleton, dict[str, object], dict[str, int]]:
    landmarks = derive_hm08_rig_landmarks(body)
    table = _joint_table(landmarks)
    name_to_index = {name: index for index, (name, _parent, _global) in enumerate(table)}
    global_by_name = {name: point for name, _parent, point in table}
    joints: list[Joint] = []
    for name, parent_name, point in table:
        parent = None if parent_name is None else name_to_index[parent_name]
        if parent_name is None:
            local = point
        else:
            parent_point = global_by_name[parent_name]
            local = tuple(point[axis] - parent_point[axis] for axis in range(3))
        joints.append(Joint(name=name, parent=parent, translation=local))
    skeleton = Skeleton(joints)
    report = validate_skeleton(skeleton)
    if report["status"] != "pass":
        raise ValueError(f"hm08 humanoid skeleton invalid: {report}")
    evidence = {
        "schema": SCHEMA,
        "joint_count": len(joints),
        "joint_names": [joint.name for joint in joints],
        "landmarks_m": {name: list(point) for name, point in sorted(landmarks.items())},
        "skeleton_validation": report,
        "truth": {
            "body_derived": True,
            "production_autorig_claim": False,
            "finger_chain_claim": False,
            "twist_bone_claim": False,
            "notes": [
                "Limb pivots are inferred from canonical body surface-region medians; torso/head pivots use front/back slice midpoints inside the body volume.",
                "Left/right limb pivots use a measured positive-X side followed by deterministic mirror symmetry.",
                "The first rig intentionally omits fingers, twist bones and correctives; those remain later production deformation gates.",
            ],
        },
    }
    return skeleton, evidence, name_to_index


def _inv_distance_weight(point, pivot, *, softness: float = 0.035) -> float:
    return 1.0 / ((_distance(point, pivot) + softness) ** 2)


def build_hm08_skin_weights(
    body: Mesh,
    skeleton: Skeleton,
    landmarks: dict[str, tuple[float, float, float]],
    name_to_index: dict[str, int],
) -> tuple[SkinWeights, dict[str, object]]:
    lo, hi = bounds(body)
    width = hi[0] - lo[0]
    height = hi[1] - lo[1]
    arm_y = lo[1] + height * 0.53
    leg_y = lo[1] + height * 0.52

    torso_names = ["pelvis", "spine_lower", "spine_mid", "chest", "neck", "head"]
    rows_joints = []
    rows_weights = []
    gate_counts = {"arm_extended": 0, "leg_extended": 0, "center_only": 0}

    for point in body.vertices:
        x, y, _z = point
        weighted_candidates: list[tuple[int, float]] = []
        for name in torso_names:
            weighted_candidates.append((name_to_index[name], _inv_distance_weight(point, landmarks[name])))

        arm_gate = _smoothstep(width * 0.07, width * 0.20, abs(x)) * _smoothstep(
            arm_y - height * 0.08, arm_y + height * 0.04, y
        )
        if arm_gate > 0.0:
            side = "right" if x >= 0.0 else "left"
            for name in (f"{side}_clavicle", f"{side}_upper_arm", f"{side}_forearm", f"{side}_hand"):
                weighted_candidates.append((name_to_index[name], arm_gate * _inv_distance_weight(point, landmarks[name])))
            gate_counts["arm_extended"] += 1

        leg_gate = _smoothstep(width * 0.015, width * 0.10, abs(x)) * (
            1.0 - _smoothstep(leg_y - height * 0.02, leg_y + height * 0.08, y)
        )
        if leg_gate > 0.0:
            side = "right" if x >= 0.0 else "left"
            for name in (f"{side}_thigh", f"{side}_shin", f"{side}_foot", f"{side}_toe"):
                weighted_candidates.append((name_to_index[name], leg_gate * _inv_distance_weight(point, landmarks[name])))
            gate_counts["leg_extended"] += 1

        if arm_gate <= 0.0 and leg_gate <= 0.0:
            gate_counts["center_only"] += 1

        weighted_candidates.sort(key=lambda row: (-row[1], row[0]))
        pairs = weighted_candidates[:4]
        total = sum(value for _joint, value in pairs)
        if total <= 1e-12:
            pairs = [(name_to_index["pelvis"], 1.0)]
            total = 1.0
        pairs = [(joint, value / total) for joint, value in pairs]
        while len(pairs) < 4:
            pairs.append((0, 0.0))
        rows_joints.append(tuple(joint for joint, _value in pairs[:4]))
        rows_weights.append(tuple(value for _joint, value in pairs[:4]))

    weights = normalize_weights(SkinWeights(rows_joints, rows_weights))
    report = validate_skin_weights(weights, vertex_count=len(body.vertices), joint_count=len(skeleton.joints))
    if report["status"] != "pass":
        raise ValueError(f"hm08 humanoid skin weights invalid: {report}")
    active_counts = [sum(1 for value in row if value > 1e-8) for row in weights.weights]
    evidence = {
        "schema": "axm.game-assets.hm08-humanoid-skin.v0.1",
        "vertex_count": len(body.vertices),
        "joint_count": len(skeleton.joints),
        "max_influences": max(active_counts),
        "mean_influences": sum(active_counts) / len(active_counts),
        "continuous_gate_counts": gate_counts,
        "validation": report,
        "truth": {
            "deterministic": True,
            "production_skinning_claim": False,
            "corrective_shapes_claim": False,
            "notes": [
                "Torso/head influence always remains available. Arm and leg neighborhoods fade in continuously by lateral position and body height instead of switching at a hard mesh seam.",
                "The weighting method is a first native skinning substrate and must graduate through real deformation views before production use.",
            ],
        },
    }
    return weights, evidence


def axis_angle_quaternion(axis: tuple[float, float, float], degrees: float):
    length = sqrt(sum(value * value for value in axis))
    if length <= 1e-12:
        raise ValueError("axis-angle needs non-zero axis")
    half = radians(degrees) * 0.5
    s = sin(half) / length
    return axis[0] * s, axis[1] * s, axis[2] * s, cos(half)


def diagnostic_pose(bind: Skeleton, name_to_index: dict[str, int]) -> Skeleton:
    joints = list(bind.joints)
    edits = {
        "left_upper_arm": ((0.0, 0.0, 1.0), -16.0),
        "right_upper_arm": ((0.0, 0.0, 1.0), 16.0),
        "left_forearm": ((0.0, 0.0, 1.0), -34.0),
        "right_forearm": ((0.0, 0.0, 1.0), 34.0),
        "left_shin": ((1.0, 0.0, 0.0), 24.0),
        "right_shin": ((1.0, 0.0, 0.0), -18.0),
        "spine_mid": ((0.0, 1.0, 0.0), 8.0),
    }
    for name, (axis, angle) in edits.items():
        index = name_to_index[name]
        joints[index] = replace(joints[index], rotation=axis_angle_quaternion(axis, angle))
    return Skeleton(joints)


def _unique_edges(mesh: Mesh):
    rows = set()
    for face in mesh.faces:
        for i, a in enumerate(face):
            b = face[(i + 1) % len(face)]
            rows.add(tuple(sorted((a, b))))
    return sorted(rows)


def deformation_evidence(mesh: Mesh, weights: SkinWeights, bind: Skeleton, posed: Skeleton) -> dict[str, object]:
    bind_vertices = skin_vertices(mesh, weights, bind, bind)
    posed_vertices = skin_vertices(mesh, weights, bind, posed)
    bind_error = max(_distance(a, b) for a, b in zip(mesh.vertices, bind_vertices))
    displacements = [_distance(a, b) for a, b in zip(mesh.vertices, posed_vertices)]
    edge_ratios = []
    for a, b in _unique_edges(mesh):
        source = _distance(mesh.vertices[a], mesh.vertices[b])
        target = _distance(posed_vertices[a], posed_vertices[b])
        if source > 1e-8:
            edge_ratios.append(target / source)
    edge_ratios.sort()

    def pct(fraction: float):
        return edge_ratios[min(len(edge_ratios) - 1, round((len(edge_ratios) - 1) * fraction))]

    return {
        "bind_reconstruction_max_error_m": bind_error,
        "posed_max_displacement_m": max(displacements),
        "posed_mean_displacement_m": sum(displacements) / len(displacements),
        "edge_ratio": {
            "min": min(edge_ratios),
            "p01": pct(0.01),
            "median": pct(0.50),
            "p99": pct(0.99),
            "max": max(edge_ratios),
        },
        "edges_over_2x": sum(value > 2.0 for value in edge_ratios),
        "edges_under_half": sum(value < 0.5 for value in edge_ratios),
        "finite": all(all(abs(value) < 1e6 for value in point) for point in posed_vertices),
        "truth": {
            "diagnostic_pose_only": True,
            "production_deformation_claim": False,
            "notes": [
                "Edge stretch/compression is a structural diagnostic, not a beauty or anatomical-quality score.",
                "Real shoulder/elbow/knee deformation close-ups and corrective-shape gates remain required before production promotion.",
            ],
        },
    }


def build_preferred_hm08_humanoid_rig():
    body_m, _uv, target_state = _load_identity_body()
    landmarks = derive_hm08_rig_landmarks(body_m)
    skeleton, skeleton_evidence, name_to_index = build_hm08_humanoid_skeleton(body_m)
    weights, skin_evidence = build_hm08_skin_weights(body_m, skeleton, landmarks, name_to_index)
    posed = diagnostic_pose(skeleton, name_to_index)
    deformation = deformation_evidence(body_m, weights, skeleton, posed)
    return body_m, skeleton, weights, posed, {
        "schema": SCHEMA,
        "target_state": target_state,
        "skeleton": skeleton_evidence,
        "skin": skin_evidence,
        "deformation": deformation,
        "joint_indices": name_to_index,
    }


if __name__ == "__main__":
    _body, _skeleton, _weights, _posed, evidence = build_preferred_hm08_humanoid_rig()
    print(json.dumps(evidence, indent=2, sort_keys=True))
