#!/usr/bin/env python3
"""AXM reconstructable fixed-topology parametric asset state v0.1.

Designed for human/creature seed meshes but generic to any canonical topology.
Sparse targets remain separate source layers; a variant is reproducible from the
seed mesh + exact target digests + weights.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from math import isfinite
from typing import Mapping, Sequence

from native_geometry import Mesh
from native_morph import MorphTarget
from native_targets import SparseTarget, mix_targets, target_digest, to_morph_target, validate_target

SCHEMA = "axm.game-assets.parametric-state.v0.1"


def _digest(value: object) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def topology_digest(mesh: Mesh) -> str:
    return _digest({"vertices": len(mesh.vertices), "faces": [list(face) for face in mesh.faces]})


def geometry_digest(mesh: Mesh) -> str:
    return _digest({
        "name": mesh.name,
        "vertices": [[float(x), float(y), float(z)] for x, y, z in mesh.vertices],
        "faces": [list(face) for face in mesh.faces],
    })


@dataclass(slots=True)
class ParametricVariant:
    mesh: Mesh
    state: dict[str, object]


def validate_library(seed_mesh: Mesh, targets: Mapping[str, SparseTarget]) -> dict[str, object]:
    failures: list[str] = []
    if len(targets) != len(set(targets)):
        failures.append("target names must be unique")
    reports = {}
    for name in sorted(targets):
        target = targets[name]
        if target.name != name:
            failures.append(f"library key {name!r} does not match target name {target.name!r}")
        report = validate_target(target, vertex_count=len(seed_mesh.vertices))
        reports[name] = report
        if report["status"] != "pass":
            failures.extend(f"{name}: {failure}" for failure in report["failures"])
    return {
        "status": "pass" if not failures else "fail",
        "failures": failures,
        "seed_vertices": len(seed_mesh.vertices),
        "seed_faces": len(seed_mesh.faces),
        "topology_digest": topology_digest(seed_mesh),
        "targets": reports,
    }


def build_variant(
    seed_mesh: Mesh,
    targets: Mapping[str, SparseTarget],
    weights: Mapping[str, float],
    *,
    seed_id: str,
    seed_source: str | None = None,
    seed_license: str | None = None,
    unit_meters: float | None = None,
    name: str | None = None,
) -> ParametricVariant:
    if not seed_id.strip():
        raise ValueError("seed_id is required")
    if unit_meters is not None and (not isfinite(unit_meters) or unit_meters <= 0.0):
        raise ValueError("unit_meters must be positive when supplied")
    library_report = validate_library(seed_mesh, targets)
    if library_report["status"] != "pass":
        raise ValueError(f"invalid target library: {library_report}")
    mixed, mix_state = mix_targets(seed_mesh, targets, weights, name=name or seed_mesh.name)
    if topology_digest(mixed) != topology_digest(seed_mesh):
        raise AssertionError("target mixing silently changed canonical topology")
    active = []
    for target_name in sorted(weights):
        weight = float(weights[target_name])
        if weight == 0.0:
            continue
        active.append({
            "name": target_name,
            "weight": weight,
            "target_digest": target_digest(targets[target_name]),
            "source": targets[target_name].source,
            "license": targets[target_name].license,
        })
    state: dict[str, object] = {
        "schema": SCHEMA,
        "seed": {
            "id": seed_id,
            "name": seed_mesh.name,
            "source": seed_source,
            "license": seed_license,
            "unit_meters": unit_meters,
            "topology_digest": topology_digest(seed_mesh),
            "geometry_digest": geometry_digest(seed_mesh),
        },
        "active_targets": active,
        "target_mix_digest": mix_state["digest"],
        "result": {
            "name": mixed.name,
            "topology_digest": topology_digest(mixed),
            "geometry_digest": geometry_digest(mixed),
            "vertices": len(mixed.vertices),
            "faces": len(mixed.faces),
        },
        "truth": {
            "reconstructable": True,
            "topology_preserved": True,
            "notes": [
                "Target weights are source-state parameters, not baked provenance-free edits.",
                "Targets are applied before topology-changing subdivision/retopology stages.",
            ],
        },
    }
    state["state_digest"] = _digest(state)
    return ParametricVariant(mixed, state)


def rebuild_variant(seed_mesh: Mesh, targets: Mapping[str, SparseTarget], state: Mapping[str, object]) -> ParametricVariant:
    if state.get("schema") != SCHEMA:
        raise ValueError(f"unsupported parametric state schema {state.get('schema')}")
    seed = state.get("seed")
    if not isinstance(seed, Mapping):
        raise ValueError("state seed is missing")
    expected_topology = seed.get("topology_digest")
    expected_geometry = seed.get("geometry_digest")
    if topology_digest(seed_mesh) != expected_topology:
        raise ValueError("seed topology digest differs from recorded state")
    if geometry_digest(seed_mesh) != expected_geometry:
        raise ValueError("seed geometry digest differs from recorded state")
    active = state.get("active_targets", [])
    if not isinstance(active, Sequence):
        raise ValueError("active_targets must be a sequence")
    weights: dict[str, float] = {}
    for item in active:
        if not isinstance(item, Mapping):
            raise ValueError("active target entry must be an object")
        name = str(item.get("name", ""))
        if name not in targets:
            raise ValueError(f"recorded target {name!r} is unavailable")
        if target_digest(targets[name]) != item.get("target_digest"):
            raise ValueError(f"target {name!r} digest changed")
        weights[name] = float(item.get("weight", 0.0))
    rebuilt = build_variant(
        seed_mesh,
        targets,
        weights,
        seed_id=str(seed.get("id", "")),
        seed_source=seed.get("source") if isinstance(seed.get("source"), str) else None,
        seed_license=seed.get("license") if isinstance(seed.get("license"), str) else None,
        unit_meters=float(seed["unit_meters"]) if seed.get("unit_meters") is not None else None,
        name=str(state.get("result", {}).get("name", seed_mesh.name)) if isinstance(state.get("result"), Mapping) else seed_mesh.name,
    )
    expected_result = state.get("result")
    if isinstance(expected_result, Mapping) and rebuilt.state["result"]["geometry_digest"] != expected_result.get("geometry_digest"):
        raise ValueError("rebuilt geometry does not match recorded result digest")
    return rebuilt


def target_channels(targets: Mapping[str, SparseTarget], names: Sequence[str], *, vertex_count: int) -> list[MorphTarget]:
    result = []
    for name in names:
        if name not in targets:
            raise ValueError(f"unknown target {name!r}")
        result.append(to_morph_target(targets[name], vertex_count=vertex_count))
    return result
