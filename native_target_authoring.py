#!/usr/bin/env python3
"""AXM native sparse-target authoring helpers v0.1.

Creates reusable fixed-topology delta targets from spatial masks instead of
baking deformations destructively into one mesh.
"""
from __future__ import annotations

from math import exp, isfinite
from typing import Callable

from native_geometry import Mesh, Vec3, vertex_normals
from native_targets import SparseTarget

WeightFn = Callable[[int, Vec3], float]
OffsetFn = Callable[[int, Vec3, Vec3], Vec3]


def gaussian_region(center: Vec3, radius: Vec3) -> WeightFn:
    if any(value <= 0.0 or not isfinite(value) for value in radius):
        raise ValueError("gaussian region radii must be positive finite values")

    def weight(_: int, point: Vec3) -> float:
        distance = sum(((point[axis] - center[axis]) / radius[axis]) ** 2 for axis in range(3))
        return exp(-0.5 * distance)

    return weight


def box_region(lo: Vec3, hi: Vec3, *, feather: float = 0.0) -> WeightFn:
    if any(hi[axis] < lo[axis] for axis in range(3)):
        raise ValueError("box region max must be >= min")
    if feather < 0.0:
        raise ValueError("feather must be non-negative")

    def weight(_: int, point: Vec3) -> float:
        if any(point[axis] < lo[axis] - feather or point[axis] > hi[axis] + feather for axis in range(3)):
            return 0.0
        if feather <= 1e-12:
            return 1.0 if all(lo[axis] <= point[axis] <= hi[axis] for axis in range(3)) else 0.0
        result = 1.0
        for axis in range(3):
            if point[axis] < lo[axis]:
                result *= max(0.0, 1.0 - (lo[axis] - point[axis]) / feather)
            elif point[axis] > hi[axis]:
                result *= max(0.0, 1.0 - (point[axis] - hi[axis]) / feather)
        return result

    return weight


def author_offset_target(
    mesh: Mesh,
    name: str,
    offset: Vec3,
    *,
    region: WeightFn,
    threshold: float = 1e-4,
    source: str | None = "AXM native target authoring",
) -> SparseTarget:
    if not name.strip():
        raise ValueError("target name must be non-empty")
    if not all(isfinite(value) for value in offset):
        raise ValueError("offset must be finite")
    deltas: dict[int, Vec3] = {}
    for index, point in enumerate(mesh.vertices):
        weight = max(0.0, min(1.0, float(region(index, point))))
        delta = tuple(offset[axis] * weight for axis in range(3))
        if any(abs(value) > threshold for value in delta):
            deltas[index] = delta  # type: ignore[assignment]
    return SparseTarget(name, deltas, source=source, license="AXM code", metadata={"authoring": "offset", "threshold": threshold})


def author_normal_target(
    mesh: Mesh,
    name: str,
    distance: float,
    *,
    region: WeightFn,
    threshold: float = 1e-4,
    source: str | None = "AXM native target authoring",
) -> SparseTarget:
    if not isfinite(distance):
        raise ValueError("normal displacement distance must be finite")
    normals = vertex_normals(mesh)
    deltas: dict[int, Vec3] = {}
    for index, (point, normal) in enumerate(zip(mesh.vertices, normals)):
        weight = max(0.0, min(1.0, float(region(index, point))))
        delta = tuple(normal[axis] * distance * weight for axis in range(3))
        if any(abs(value) > threshold for value in delta):
            deltas[index] = delta  # type: ignore[assignment]
    return SparseTarget(name, deltas, source=source, license="AXM code", metadata={"authoring": "normal", "threshold": threshold})


def author_custom_target(
    mesh: Mesh,
    name: str,
    *,
    region: WeightFn,
    offset_fn: OffsetFn,
    threshold: float = 1e-4,
    source: str | None = "AXM native target authoring",
) -> SparseTarget:
    normals = vertex_normals(mesh)
    deltas: dict[int, Vec3] = {}
    for index, (point, normal) in enumerate(zip(mesh.vertices, normals)):
        weight = max(0.0, min(1.0, float(region(index, point))))
        raw = offset_fn(index, point, normal)
        if len(raw) != 3 or not all(isfinite(value) for value in raw):
            raise ValueError(f"custom offset at vertex {index} is invalid")
        delta = tuple(raw[axis] * weight for axis in range(3))
        if any(abs(value) > threshold for value in delta):
            deltas[index] = delta  # type: ignore[assignment]
    return SparseTarget(name, deltas, source=source, license="AXM code", metadata={"authoring": "custom", "threshold": threshold})
