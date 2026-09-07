#!/usr/bin/env python3
"""AXM native skeleton, skin-weight, and deformation state v0.1."""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite, sqrt
from typing import Sequence

from native_geometry import Mesh, Vec3

Quat = tuple[float, float, float, float]
Vec4i = tuple[int, int, int, int]
Vec4f = tuple[float, float, float, float]
Mat4 = tuple[
    tuple[float, float, float, float],
    tuple[float, float, float, float],
    tuple[float, float, float, float],
    tuple[float, float, float, float],
]
IDENTITY: Mat4 = (
    (1.0, 0.0, 0.0, 0.0),
    (0.0, 1.0, 0.0, 0.0),
    (0.0, 0.0, 1.0, 0.0),
    (0.0, 0.0, 0.0, 1.0),
)


@dataclass(frozen=True, slots=True)
class Joint:
    name: str
    parent: int | None = None
    translation: Vec3 = (0.0, 0.0, 0.0)
    rotation: Quat = (0.0, 0.0, 0.0, 1.0)
    scale: Vec3 = (1.0, 1.0, 1.0)


@dataclass(slots=True)
class Skeleton:
    joints: list[Joint]


@dataclass(slots=True)
class SkinWeights:
    joints: list[Vec4i]
    weights: list[Vec4f]


def _finite(values: Sequence[float]) -> bool:
    return all(isfinite(float(v)) for v in values)


def _quat_length(q: Quat) -> float:
    return sqrt(sum(v * v for v in q))


def normalize_quaternion(q: Quat) -> Quat:
    length = _quat_length(q)
    if length <= 1e-12:
        raise ValueError("zero-length quaternion")
    return tuple(v / length for v in q)  # type: ignore[return-value]


def validate_skeleton(skeleton: Skeleton, *, require_single_root: bool = True) -> dict[str, object]:
    failures: list[str] = []
    joints = skeleton.joints
    if not joints:
        failures.append("skeleton has no joints")
        return {"status": "fail", "failures": failures, "roots": []}
    names = [joint.name for joint in joints]
    if any(not name.strip() for name in names):
        failures.append("joint names must be non-empty")
    if len(names) != len(set(names)):
        failures.append("joint names must be unique")
    roots: list[int] = []
    for index, joint in enumerate(joints):
        if joint.parent is None:
            roots.append(index)
        elif joint.parent < 0 or joint.parent >= len(joints):
            failures.append(f"joint {index} parent outside skeleton")
        elif joint.parent == index:
            failures.append(f"joint {index} cannot parent itself")
        if not _finite(joint.translation + joint.rotation + joint.scale):
            failures.append(f"joint {index} contains non-finite transform")
        qlen = _quat_length(joint.rotation)
        if abs(qlen - 1.0) > 1e-5:
            failures.append(f"joint {index} quaternion must be normalized")
        if any(abs(v) <= 1e-12 for v in joint.scale):
            failures.append(f"joint {index} scale must be non-zero")

    for start in range(len(joints)):
        seen: set[int] = set()
        current: int | None = start
        while current is not None and 0 <= current < len(joints):
            if current in seen:
                failures.append(f"joint hierarchy cycle reachable from {start}")
                break
            seen.add(current)
            current = joints[current].parent
    if require_single_root and len(roots) != 1:
        failures.append(f"native skin v0.1 requires one root, found {len(roots)}")
    return {"status": "pass" if not failures else "fail", "failures": failures, "roots": roots}


def normalize_weights(weights: SkinWeights) -> SkinWeights:
    normalized: list[Vec4f] = []
    normalized_joints: list[Vec4i] = []
    if len(weights.joints) != len(weights.weights):
        raise ValueError("joint/weight vertex counts differ")
    for joint_row, weight_row in zip(weights.joints, weights.weights):
        pairs = [(int(j), max(0.0, float(w))) for j, w in zip(joint_row, weight_row) if w > 0.0]
        pairs.sort(key=lambda pair: (-pair[1], pair[0]))
        pairs = pairs[:4]
        total = sum(w for _, w in pairs)
        if total <= 1e-12:
            pairs = [(0, 1.0)]
            total = 1.0
        pairs = [(j, w / total) for j, w in pairs]
        while len(pairs) < 4:
            pairs.append((0, 0.0))
        normalized_joints.append(tuple(j for j, _ in pairs))  # type: ignore[arg-type]
        normalized.append(tuple(w for _, w in pairs))  # type: ignore[arg-type]
    return SkinWeights(normalized_joints, normalized)


def validate_skin_weights(weights: SkinWeights, *, vertex_count: int, joint_count: int, tolerance: float = 1e-6) -> dict[str, object]:
    failures: list[str] = []
    if len(weights.joints) != vertex_count or len(weights.weights) != vertex_count:
        failures.append(f"skin rows must equal vertex count {vertex_count}")
    rows = min(len(weights.joints), len(weights.weights), vertex_count)
    for vertex in range(rows):
        joints = weights.joints[vertex]
        values = weights.weights[vertex]
        if len(joints) != 4 or len(values) != 4:
            failures.append(f"vertex {vertex} must contain exactly four joint/weight slots")
            continue
        if not _finite(values):
            failures.append(f"vertex {vertex} has non-finite weight")
            continue
        if any(value < 0.0 for value in values):
            failures.append(f"vertex {vertex} has negative weight")
        active: list[int] = []
        for joint, value in zip(joints, values):
            if value <= 0.0:
                continue
            if joint < 0 or joint >= joint_count:
                failures.append(f"vertex {vertex} joint {joint} outside skin")
            if joint in active:
                failures.append(f"vertex {vertex} repeats non-zero joint {joint}")
            active.append(joint)
        total = sum(values)
        if abs(total - 1.0) > tolerance:
            failures.append(f"vertex {vertex} weight sum {total:.9g} differs from 1")
    return {"status": "pass" if not failures else "fail", "failures": failures, "vertices": vertex_count, "joints": joint_count}


def trs_matrix(translation: Vec3, rotation: Quat, scale: Vec3) -> Mat4:
    x, y, z, w = normalize_quaternion(rotation)
    sx, sy, sz = scale
    xx, yy, zz = x * x, y * y, z * z
    xy, xz, yz = x * y, x * z, y * z
    wx, wy, wz = w * x, w * y, w * z
    r00 = 1.0 - 2.0 * (yy + zz)
    r01 = 2.0 * (xy - wz)
    r02 = 2.0 * (xz + wy)
    r10 = 2.0 * (xy + wz)
    r11 = 1.0 - 2.0 * (xx + zz)
    r12 = 2.0 * (yz - wx)
    r20 = 2.0 * (xz - wy)
    r21 = 2.0 * (yz + wx)
    r22 = 1.0 - 2.0 * (xx + yy)
    tx, ty, tz = translation
    return (
        (r00 * sx, r01 * sy, r02 * sz, tx),
        (r10 * sx, r11 * sy, r12 * sz, ty),
        (r20 * sx, r21 * sy, r22 * sz, tz),
        (0.0, 0.0, 0.0, 1.0),
    )


def matmul(a: Mat4, b: Mat4) -> Mat4:
    return tuple(
        tuple(sum(a[row][k] * b[k][col] for k in range(4)) for col in range(4))
        for row in range(4)
    )  # type: ignore[return-value]


def inverse4(matrix: Mat4) -> Mat4:
    work = [list(row) + [1.0 if row_index == col else 0.0 for col in range(4)] for row_index, row in enumerate(matrix)]
    for col in range(4):
        pivot = max(range(col, 4), key=lambda row: abs(work[row][col]))
        if abs(work[pivot][col]) <= 1e-12:
            raise ValueError("non-invertible bind matrix")
        if pivot != col:
            work[col], work[pivot] = work[pivot], work[col]
        scale = work[col][col]
        work[col] = [value / scale for value in work[col]]
        for row in range(4):
            if row == col:
                continue
            factor = work[row][col]
            if abs(factor) <= 1e-18:
                continue
            work[row] = [value - factor * pivot_value for value, pivot_value in zip(work[row], work[col])]
    return tuple(tuple(row[4:8]) for row in work)  # type: ignore[return-value]


def global_joint_matrices(skeleton: Skeleton) -> list[Mat4]:
    report = validate_skeleton(skeleton)
    if report["status"] != "pass":
        raise ValueError(f"invalid skeleton: {report}")
    cache: list[Mat4 | None] = [None] * len(skeleton.joints)

    def resolve(index: int) -> Mat4:
        cached = cache[index]
        if cached is not None:
            return cached
        joint = skeleton.joints[index]
        local = trs_matrix(joint.translation, joint.rotation, joint.scale)
        result = local if joint.parent is None else matmul(resolve(joint.parent), local)
        cache[index] = result
        return result

    return [resolve(index) for index in range(len(skeleton.joints))]


def inverse_bind_matrices(skeleton: Skeleton) -> list[Mat4]:
    return [inverse4(matrix) for matrix in global_joint_matrices(skeleton)]


def transform_point(matrix: Mat4, point: Vec3) -> Vec3:
    x, y, z = point
    values = (x, y, z, 1.0)
    result = [sum(matrix[row][col] * values[col] for col in range(4)) for row in range(4)]
    if abs(result[3]) > 1e-12 and abs(result[3] - 1.0) > 1e-12:
        return result[0] / result[3], result[1] / result[3], result[2] / result[3]
    return result[0], result[1], result[2]


def skin_vertices(mesh: Mesh, weights: SkinWeights, bind_skeleton: Skeleton, posed_skeleton: Skeleton) -> list[Vec3]:
    if len(bind_skeleton.joints) != len(posed_skeleton.joints):
        raise ValueError("bind and posed skeleton joint counts differ")
    validation = validate_skin_weights(weights, vertex_count=len(mesh.vertices), joint_count=len(bind_skeleton.joints))
    if validation["status"] != "pass":
        raise ValueError(f"invalid skin weights: {validation}")
    inverse_bind = inverse_bind_matrices(bind_skeleton)
    posed_global = global_joint_matrices(posed_skeleton)
    skin_matrices = [matmul(pose, inv) for pose, inv in zip(posed_global, inverse_bind)]
    output: list[Vec3] = []
    for point, joints, values in zip(mesh.vertices, weights.joints, weights.weights):
        accum = [0.0, 0.0, 0.0]
        for joint, weight in zip(joints, values):
            if weight <= 0.0:
                continue
            transformed = transform_point(skin_matrices[joint], point)
            accum[0] += transformed[0] * weight
            accum[1] += transformed[1] * weight
            accum[2] += transformed[2] * weight
        output.append((accum[0], accum[1], accum[2]))
    return output


def flatten_matrix_column_major(matrix: Mat4) -> tuple[float, ...]:
    return tuple(matrix[row][col] for col in range(4) for row in range(4))
