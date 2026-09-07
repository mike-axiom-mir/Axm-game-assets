#!/usr/bin/env python3
"""AXM native constraint-cloth and collision evidence v0.1.

A deterministic position-based cloth substrate for source state and secondary
motion experiments. It owns pins, rest constraints, simulation state and
technical receipts. It is not a claim of production garment simulation.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite, sqrt
from typing import Sequence

from native_geometry import Mesh, Vec3


@dataclass(frozen=True, slots=True)
class DistanceConstraint:
    a: int
    b: int
    rest: float
    stiffness: float
    kind: str


@dataclass(frozen=True, slots=True)
class SphereCollider:
    center: Vec3
    radius: float


@dataclass(slots=True)
class ClothSystem:
    mesh: Mesh
    positions: list[Vec3]
    previous: list[Vec3]
    pins: dict[int, Vec3]
    constraints: list[DistanceConstraint]
    gravity: Vec3 = (0.0, -9.81, 0.0)
    damping: float = 0.015
    thickness: float = 0.008


def _distance(a: Vec3, b: Vec3) -> float:
    return sqrt(sum((b[axis] - a[axis]) ** 2 for axis in range(3)))


def _add_constraint(constraints: list[DistanceConstraint], positions: Sequence[Vec3], a: int, b: int, stiffness: float, kind: str) -> None:
    rest = _distance(positions[a], positions[b])
    if rest <= 1e-12:
        raise ValueError(f"zero-length cloth constraint {a}-{b}")
    constraints.append(DistanceConstraint(a, b, rest, stiffness, kind))


def make_cloth_grid(
    width: float = 0.8,
    depth: float = 0.8,
    *,
    columns: int = 12,
    rows: int = 12,
    height: float = 0.55,
    pin_edge: str = "back",
    structural_stiffness: float = 1.0,
    shear_stiffness: float = 0.7,
    bend_stiffness: float = 0.35,
    name: str = "cloth_grid",
) -> ClothSystem:
    if width <= 0.0 or depth <= 0.0:
        raise ValueError("cloth dimensions must be positive")
    if columns < 2 or rows < 2:
        raise ValueError("cloth grid needs at least 2x2 cells")
    vertices: list[Vec3] = []
    for row in range(rows + 1):
        z = (row / rows - 0.5) * depth
        for column in range(columns + 1):
            x = (column / columns - 0.5) * width
            vertices.append((x, height, z))

    def index(column: int, row: int) -> int:
        return row * (columns + 1) + column

    faces = []
    for row in range(rows):
        for column in range(columns):
            a = index(column, row)
            b = index(column + 1, row)
            c = index(column + 1, row + 1)
            d = index(column, row + 1)
            faces.append((a, b, c, d))

    constraints: list[DistanceConstraint] = []
    for row in range(rows + 1):
        for column in range(columns + 1):
            here = index(column, row)
            if column < columns:
                _add_constraint(constraints, vertices, here, index(column + 1, row), structural_stiffness, "structural")
            if row < rows:
                _add_constraint(constraints, vertices, here, index(column, row + 1), structural_stiffness, "structural")
            if column < columns and row < rows:
                _add_constraint(constraints, vertices, here, index(column + 1, row + 1), shear_stiffness, "shear")
                _add_constraint(constraints, vertices, index(column + 1, row), index(column, row + 1), shear_stiffness, "shear")
            if column + 2 <= columns:
                _add_constraint(constraints, vertices, here, index(column + 2, row), bend_stiffness, "bend")
            if row + 2 <= rows:
                _add_constraint(constraints, vertices, here, index(column, row + 2), bend_stiffness, "bend")

    if pin_edge == "back":
        pin_indices = [index(column, 0) for column in range(columns + 1)]
    elif pin_edge == "front":
        pin_indices = [index(column, rows) for column in range(columns + 1)]
    elif pin_edge == "left":
        pin_indices = [index(0, row) for row in range(rows + 1)]
    elif pin_edge == "right":
        pin_indices = [index(columns, row) for row in range(rows + 1)]
    else:
        raise ValueError("pin_edge must be back/front/left/right")
    pins = {vertex: vertices[vertex] for vertex in pin_indices}
    mesh = Mesh(name, list(vertices), faces)
    return ClothSystem(mesh, list(vertices), list(vertices), pins, constraints)


def copy_cloth(system: ClothSystem) -> ClothSystem:
    return ClothSystem(
        Mesh(system.mesh.name, list(system.mesh.vertices), list(system.mesh.faces)),
        list(system.positions),
        list(system.previous),
        dict(system.pins),
        list(system.constraints),
        gravity=system.gravity,
        damping=system.damping,
        thickness=system.thickness,
    )


def _project_sphere(point: Vec3, collider: SphereCollider, thickness: float) -> Vec3:
    cx, cy, cz = collider.center
    dx, dy, dz = point[0] - cx, point[1] - cy, point[2] - cz
    distance = sqrt(dx * dx + dy * dy + dz * dz)
    target = collider.radius + thickness
    if distance >= target:
        return point
    if distance <= 1e-12:
        return (cx, cy + target, cz)
    scale = target / distance
    return (cx + dx * scale, cy + dy * scale, cz + dz * scale)


def step_cloth(
    system: ClothSystem,
    dt: float,
    *,
    iterations: int = 8,
    colliders: Sequence[SphereCollider] = (),
) -> None:
    if dt <= 0.0 or not isfinite(dt):
        raise ValueError("cloth dt must be positive and finite")
    if iterations < 1:
        raise ValueError("cloth solver needs at least one iteration")
    if not (0.0 <= system.damping < 1.0):
        raise ValueError("cloth damping must be within [0,1)")
    if system.thickness < 0.0:
        raise ValueError("cloth thickness must be non-negative")
    gx, gy, gz = system.gravity
    dt2 = dt * dt
    old_positions = list(system.positions)
    predicted = list(system.positions)
    for index, point in enumerate(system.positions):
        if index in system.pins:
            predicted[index] = system.pins[index]
            continue
        previous = system.previous[index]
        velocity = tuple((point[axis] - previous[axis]) * (1.0 - system.damping) for axis in range(3))
        predicted[index] = (
            point[0] + velocity[0] + gx * dt2,
            point[1] + velocity[1] + gy * dt2,
            point[2] + velocity[2] + gz * dt2,
        )
    system.previous = old_positions
    system.positions = predicted

    for _ in range(iterations):
        for constraint in system.constraints:
            a, b = constraint.a, constraint.b
            pa, pb = system.positions[a], system.positions[b]
            dx, dy, dz = pb[0] - pa[0], pb[1] - pa[1], pb[2] - pa[2]
            distance = sqrt(dx * dx + dy * dy + dz * dz)
            if distance <= 1e-12:
                continue
            factor = (distance - constraint.rest) / distance * constraint.stiffness
            correction = (dx * factor, dy * factor, dz * factor)
            a_free, b_free = a not in system.pins, b not in system.pins
            if a_free and b_free:
                system.positions[a] = tuple(pa[axis] + correction[axis] * 0.5 for axis in range(3))
                system.positions[b] = tuple(pb[axis] - correction[axis] * 0.5 for axis in range(3))
            elif a_free:
                system.positions[a] = tuple(pa[axis] + correction[axis] for axis in range(3))
            elif b_free:
                system.positions[b] = tuple(pb[axis] - correction[axis] for axis in range(3))

        for index, point in enumerate(system.positions):
            if index in system.pins:
                continue
            projected = point
            for collider in colliders:
                if collider.radius <= 0.0:
                    raise ValueError("sphere collider radius must be positive")
                projected = _project_sphere(projected, collider, system.thickness)
            system.positions[index] = projected
        for index, anchor in system.pins.items():
            system.positions[index] = anchor

    system.mesh.vertices = list(system.positions)


def simulate_cloth(
    system: ClothSystem,
    *,
    steps: int,
    dt: float = 1.0 / 60.0,
    iterations: int = 8,
    colliders: Sequence[SphereCollider] = (),
) -> None:
    if steps < 0:
        raise ValueError("cloth steps must be non-negative")
    for _ in range(steps):
        step_cloth(system, dt, iterations=iterations, colliders=colliders)


def cloth_evidence(system: ClothSystem, *, colliders: Sequence[SphereCollider] = ()) -> dict[str, object]:
    max_pin_drift = 0.0
    for index, anchor in system.pins.items():
        max_pin_drift = max(max_pin_drift, _distance(system.positions[index], anchor))

    strains = []
    kinds: dict[str, list[float]] = {}
    for constraint in system.constraints:
        current = _distance(system.positions[constraint.a], system.positions[constraint.b])
        strain = abs(current - constraint.rest) / constraint.rest
        strains.append(strain)
        kinds.setdefault(constraint.kind, []).append(strain)

    max_penetration = 0.0
    for collider in colliders:
        target = collider.radius + system.thickness
        for index, point in enumerate(system.positions):
            if index in system.pins:
                continue
            penetration = target - _distance(point, collider.center)
            max_penetration = max(max_penetration, penetration)
    max_penetration = max(0.0, max_penetration)

    return {
        "vertices": len(system.positions),
        "faces": len(system.mesh.faces),
        "pins": len(system.pins),
        "constraints": len(system.constraints),
        "max_pin_drift": max_pin_drift,
        "max_constraint_strain": max(strains, default=0.0),
        "mean_constraint_strain": sum(strains) / len(strains) if strains else 0.0,
        "strain_by_kind": {
            kind: {"max": max(values), "mean": sum(values) / len(values)}
            for kind, values in sorted(kinds.items())
        },
        "max_sphere_penetration": max_penetration,
        "bounds_y": [min((point[1] for point in system.positions), default=0.0), max((point[1] for point in system.positions), default=0.0)],
        "truth": "Technical PBD/Verlet evidence only. Garment tailoring, folds, self-collision, friction, aero and production cloth quality remain separate gates.",
    }
