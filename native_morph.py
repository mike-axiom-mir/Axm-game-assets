#!/usr/bin/env python3
"""AXM native morph/blendshape delta state v0.1."""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Sequence

from native_geometry import Mesh, Vec3


@dataclass(slots=True)
class MorphTarget:
    name: str
    position_deltas: list[Vec3]
    normal_deltas: list[Vec3] | None = None


def _finite_vec3(value: Vec3) -> bool:
    return all(isfinite(component) for component in value)


def validate_morph(target: MorphTarget, *, vertex_count: int) -> dict[str, object]:
    failures: list[str] = []
    if not target.name.strip():
        failures.append("morph target name must be non-empty")
    if len(target.position_deltas) != vertex_count:
        failures.append(f"position delta count must equal vertex count {vertex_count}")
    if target.normal_deltas is not None and len(target.normal_deltas) != vertex_count:
        failures.append(f"normal delta count must equal vertex count {vertex_count}")
    for index, delta in enumerate(target.position_deltas[:vertex_count]):
        if not _finite_vec3(delta):
            failures.append(f"position delta {index} contains non-finite value")
    if target.normal_deltas is not None:
        for index, delta in enumerate(target.normal_deltas[:vertex_count]):
            if not _finite_vec3(delta):
                failures.append(f"normal delta {index} contains non-finite value")
    return {"status": "pass" if not failures else "fail", "failures": failures, "name": target.name, "vertices": vertex_count}


def validate_morph_set(targets: Sequence[MorphTarget], *, vertex_count: int) -> dict[str, object]:
    failures: list[str] = []
    names = [target.name for target in targets]
    if len(names) != len(set(names)):
        failures.append("morph target names must be unique")
    reports = []
    for target in targets:
        report = validate_morph(target, vertex_count=vertex_count)
        reports.append(report)
        failures.extend(f"{target.name}: {failure}" for failure in report["failures"])
    return {"status": "pass" if not failures else "fail", "failures": failures, "targets": len(targets), "reports": reports}


def apply_morphs(mesh: Mesh, targets: Sequence[MorphTarget], weights: Sequence[float], *, name: str | None = None) -> Mesh:
    if len(targets) != len(weights):
        raise ValueError("morph target and weight counts differ")
    report = validate_morph_set(targets, vertex_count=len(mesh.vertices))
    if report["status"] != "pass":
        raise ValueError(f"invalid morph set: {report}")
    if not all(isfinite(weight) for weight in weights):
        raise ValueError("morph weights must be finite")
    vertices: list[Vec3] = []
    for index, base in enumerate(mesh.vertices):
        x, y, z = base
        for target, weight in zip(targets, weights):
            dx, dy, dz = target.position_deltas[index]
            x += dx * weight
            y += dy * weight
            z += dz * weight
        vertices.append((x, y, z))
    return Mesh(name or mesh.name, vertices, list(mesh.faces))


def sparse_position_deltas(target: MorphTarget, *, epsilon: float = 1e-12) -> list[tuple[int, Vec3]]:
    return [
        (index, delta)
        for index, delta in enumerate(target.position_deltas)
        if abs(delta[0]) > epsilon or abs(delta[1]) > epsilon or abs(delta[2]) > epsilon
    ]
