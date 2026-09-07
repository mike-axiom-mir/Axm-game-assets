#!/usr/bin/env python3
"""AXM sparse fixed-topology target engine v0.1.

The mechanism is intentionally generic: a target is a sparse set of vertex
position deltas applied to one canonical topology. MakeHuman-compatible .target
files are one supported text representation, but this module does not depend on
MakeHuman application code.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from math import isfinite
from pathlib import Path
from typing import Iterable, Mapping

from native_geometry import Mesh, Vec3
from native_morph import MorphTarget

SCHEMA = "axm.game-assets.sparse-target.v0.1"


@dataclass(slots=True)
class SparseTarget:
    name: str
    deltas: dict[int, Vec3]
    source: str | None = None
    license: str | None = None
    metadata: dict[str, object] = field(default_factory=dict)


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def target_digest(target: SparseTarget) -> str:
    payload = {
        "schema": SCHEMA,
        "name": target.name,
        "deltas": [[index, *target.deltas[index]] for index in sorted(target.deltas)],
        "source": target.source,
        "license": target.license,
        "metadata": target.metadata,
    }
    return "sha256:" + hashlib.sha256(_canonical(payload)).hexdigest()


def parse_target_text(
    text: str,
    *,
    name: str,
    source: str | None = None,
    license: str | None = None,
) -> SparseTarget:
    if not name.strip():
        raise ValueError("target name must be non-empty")
    deltas: dict[int, Vec3] = {}
    comments: list[str] = []
    basemesh: str | None = None
    for line_number, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line:
            continue
        if line.startswith("#"):
            comment = line[1:].strip()
            comments.append(comment)
            lower = comment.lower()
            if lower.startswith("basemesh "):
                basemesh = comment.split(None, 1)[1].strip()
            continue
        parts = line.split()
        if len(parts) != 4:
            raise ValueError(f"line {line_number}: expected vertex_index dx dy dz")
        try:
            index = int(parts[0])
            delta = (float(parts[1]), float(parts[2]), float(parts[3]))
        except ValueError as exc:
            raise ValueError(f"line {line_number}: invalid numeric target row") from exc
        if index < 0:
            raise ValueError(f"line {line_number}: vertex index must be non-negative")
        if index in deltas:
            raise ValueError(f"line {line_number}: duplicate vertex index {index}")
        if not all(isfinite(value) for value in delta):
            raise ValueError(f"line {line_number}: non-finite delta")
        deltas[index] = delta
    return SparseTarget(
        name=name,
        deltas=deltas,
        source=source,
        license=license,
        metadata={"comments": comments, "basemesh": basemesh, "rows": len(deltas)},
    )


def load_target(path: str | Path, *, name: str | None = None, source: str | None = None, license: str | None = None) -> SparseTarget:
    target_path = Path(path)
    return parse_target_text(
        target_path.read_text(encoding="utf-8"),
        name=name or target_path.stem,
        source=source or target_path.as_posix(),
        license=license,
    )


def validate_target(target: SparseTarget, *, vertex_count: int) -> dict[str, object]:
    failures: list[str] = []
    if vertex_count <= 0:
        failures.append("vertex_count must be positive")
    if not target.name.strip():
        failures.append("target name must be non-empty")
    for index, delta in target.deltas.items():
        if index < 0 or index >= vertex_count:
            failures.append(f"vertex {index} outside canonical mesh [0,{vertex_count})")
        if len(delta) != 3 or not all(isfinite(float(value)) for value in delta):
            failures.append(f"vertex {index} has invalid delta")
    return {
        "status": "pass" if not failures else "fail",
        "failures": failures,
        "name": target.name,
        "rows": len(target.deltas),
        "vertex_count": vertex_count,
        "digest": target_digest(target),
    }


def apply_target(mesh: Mesh, target: SparseTarget, weight: float, *, name: str | None = None) -> Mesh:
    if not isfinite(weight):
        raise ValueError("target weight must be finite")
    report = validate_target(target, vertex_count=len(mesh.vertices))
    if report["status"] != "pass":
        raise ValueError(f"invalid target: {report}")
    vertices = list(mesh.vertices)
    for index in sorted(target.deltas):
        dx, dy, dz = target.deltas[index]
        x, y, z = vertices[index]
        vertices[index] = (x + dx * weight, y + dy * weight, z + dz * weight)
    return Mesh(name or mesh.name, vertices, list(mesh.faces))


def mix_targets(
    mesh: Mesh,
    library: Mapping[str, SparseTarget],
    weights: Mapping[str, float],
    *,
    name: str | None = None,
) -> tuple[Mesh, dict[str, object]]:
    unknown = sorted(set(weights) - set(library))
    if unknown:
        raise ValueError(f"unknown targets: {unknown}")
    for target_name, weight in weights.items():
        if not isfinite(float(weight)):
            raise ValueError(f"target {target_name} has non-finite weight")
    vertices = [list(vertex) for vertex in mesh.vertices]
    applied: list[dict[str, object]] = []
    # Canonical name ordering makes the same weight map byte-stable regardless
    # of caller dictionary construction order.
    for target_name in sorted(weights):
        weight = float(weights[target_name])
        target = library[target_name]
        report = validate_target(target, vertex_count=len(mesh.vertices))
        if report["status"] != "pass":
            raise ValueError(f"invalid target {target_name}: {report}")
        if weight == 0.0:
            continue
        for index in sorted(target.deltas):
            delta = target.deltas[index]
            for axis in range(3):
                vertices[index][axis] += delta[axis] * weight
        applied.append({"name": target_name, "weight": weight, "digest": report["digest"], "rows": report["rows"]})
    output = Mesh(name or mesh.name, [tuple(vertex) for vertex in vertices], list(mesh.faces))
    state = {
        "schema": "axm.game-assets.target-mix.v0.1",
        "canonical_mesh": mesh.name,
        "vertex_count": len(mesh.vertices),
        "face_count": len(mesh.faces),
        "applied": applied,
    }
    state["digest"] = "sha256:" + hashlib.sha256(_canonical(state)).hexdigest()
    return output, state


def compose_targets(name: str, weighted: Iterable[tuple[SparseTarget, float]], *, source: str | None = None) -> SparseTarget:
    accum: dict[int, list[float]] = {}
    lineage = []
    for target, weight in sorted(weighted, key=lambda item: item[0].name):
        if not isfinite(float(weight)):
            raise ValueError(f"target {target.name} has non-finite weight")
        lineage.append({"name": target.name, "weight": float(weight), "digest": target_digest(target)})
        for index, delta in target.deltas.items():
            row = accum.setdefault(index, [0.0, 0.0, 0.0])
            for axis in range(3):
                row[axis] += delta[axis] * float(weight)
    deltas = {index: tuple(row) for index, row in accum.items() if any(abs(value) > 1e-15 for value in row)}
    return SparseTarget(name, deltas, source=source, metadata={"lineage": lineage})


def to_morph_target(target: SparseTarget, *, vertex_count: int) -> MorphTarget:
    report = validate_target(target, vertex_count=vertex_count)
    if report["status"] != "pass":
        raise ValueError(f"invalid target: {report}")
    deltas: list[Vec3] = [(0.0, 0.0, 0.0)] * vertex_count
    for index, delta in target.deltas.items():
        deltas[index] = delta
    return MorphTarget(target.name, deltas)
