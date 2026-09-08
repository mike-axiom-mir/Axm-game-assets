#!/usr/bin/env python3
"""Reversible static body-conforming fit pass for rigid armor meshes.

The source armor remains canonical and untouched. This delivery transform keeps
vertex/face order and UV compatibility while moving vertices only along the
nearest body vertex normal when static clearance is outside an authored band.
Primary structural plates and raised accent rails can use different bands.

This is deliberately a bounded static fit mechanism, not a replacement for
rig-space articulation, collision, or exact point-to-triangle signed distance.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import floor, sqrt

from native_geometry import Mesh, vertex_normals

SCHEMA = "axm.game-assets.armor-conform.v0.1"


@dataclass(frozen=True, slots=True)
class ConformSpec:
    clearance_min_m: float
    clearance_max_m: float
    strength: float = 0.86
    passes: int = 2
    max_step_m: float = 0.045
    cell_size_m: float = 0.035
    max_search_rings: int = 5


def _sub(a, b):
    return a[0] - b[0], a[1] - b[1], a[2] - b[2]


def _add(a, b):
    return a[0] + b[0], a[1] + b[1], a[2] + b[2]


def _mul(v, scalar: float):
    return v[0] * scalar, v[1] * scalar, v[2] * scalar


def _dot(a, b) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _length(v) -> float:
    return sqrt(_dot(v, v))


def _key(point, cell: float) -> tuple[int, int, int]:
    return tuple(int(floor(value / cell)) for value in point)


def _body_index(body: Mesh, cell: float):
    normals = vertex_normals(body)
    grid: dict[tuple[int, int, int], list[int]] = {}
    for index, point in enumerate(body.vertices):
        grid.setdefault(_key(point, cell), []).append(index)
    return normals, grid


def _nearest(point, body: Mesh, grid, cell: float, max_rings: int) -> int:
    center = _key(point, cell)
    for ring in range(max_rings + 1):
        candidates: list[int] = []
        for dx in range(-ring, ring + 1):
            for dy in range(-ring, ring + 1):
                for dz in range(-ring, ring + 1):
                    if ring > 0 and max(abs(dx), abs(dy), abs(dz)) != ring:
                        continue
                    candidates.extend(grid.get((center[0] + dx, center[1] + dy, center[2] + dz), ()))
        if candidates:
            return min(candidates, key=lambda index: _length(_sub(point, body.vertices[index])))
    return min(range(len(body.vertices)), key=lambda index: _length(_sub(point, body.vertices[index])))


def conform_armor_mesh(body: Mesh, armor: Mesh, *, spec: ConformSpec, name: str | None = None) -> tuple[Mesh, dict[str, object]]:
    if not body.vertices or not armor.vertices:
        raise ValueError("conform requires non-empty body and armor")
    if not (0.0 <= spec.clearance_min_m < spec.clearance_max_m <= 0.10):
        raise ValueError("invalid authored clearance band")
    if not (0.0 < spec.strength <= 1.0):
        raise ValueError("strength must be within (0,1]")
    if spec.passes < 1 or spec.passes > 8:
        raise ValueError("passes must be 1..8")
    if spec.max_step_m <= 0.0 or spec.max_step_m > 0.10:
        raise ValueError("max_step_m must be within (0,0.10]")

    normals, grid = _body_index(body, spec.cell_size_m)
    vertices = list(armor.vertices)
    pass_reports: list[dict[str, object]] = []
    max_total_move = [0.0] * len(vertices)

    for pass_index in range(spec.passes):
        moved = 0
        inward_repairs = 0
        float_repairs = 0
        movement_sum = 0.0
        max_move = 0.0
        updated = list(vertices)
        for index, point in enumerate(vertices):
            body_index = _nearest(point, body, grid, spec.cell_size_m, spec.max_search_rings)
            base = body.vertices[body_index]
            normal = normals[body_index]
            signed = _dot(_sub(point, base), normal)
            correction = 0.0
            if signed < spec.clearance_min_m:
                correction = spec.clearance_min_m - signed
                inward_repairs += 1
            elif signed > spec.clearance_max_m:
                correction = spec.clearance_max_m - signed
                float_repairs += 1
            if correction == 0.0:
                continue
            step = correction * spec.strength
            step = max(-spec.max_step_m, min(spec.max_step_m, step))
            updated[index] = _add(point, _mul(normal, step))
            distance = abs(step)
            movement_sum += distance
            max_move = max(max_move, distance)
            max_total_move[index] += distance
            moved += 1
        vertices = updated
        pass_reports.append({
            "pass": pass_index + 1,
            "moved_vertices": moved,
            "float_repairs": float_repairs,
            "inward_repairs": inward_repairs,
            "mean_step_m": movement_sum / float(max(moved, 1)),
            "max_step_m": max_move,
        })

    output = Mesh(name or f"{armor.name}_conformed", vertices, list(armor.faces))
    changed = [value for value in max_total_move if value > 0.0]
    evidence = {
        "schema": SCHEMA,
        "source_mesh": armor.name,
        "source_vertices": len(armor.vertices),
        "source_faces": len(armor.faces),
        "topology_preserved": output.faces == armor.faces and len(output.vertices) == len(armor.vertices),
        "vertex_order_preserved": len(output.vertices) == len(armor.vertices),
        "spec": {
            "clearance_min_m": spec.clearance_min_m,
            "clearance_max_m": spec.clearance_max_m,
            "strength": spec.strength,
            "passes": spec.passes,
            "max_step_m": spec.max_step_m,
            "cell_size_m": spec.cell_size_m,
        },
        "passes": pass_reports,
        "moved_vertex_count": len(changed),
        "max_accumulated_move_m": max(changed) if changed else 0.0,
        "mean_accumulated_move_m": sum(changed) / float(max(len(changed), 1)),
        "truth": {
            "canonical_source_mutated": False,
            "exact_surface_distance_claim": False,
            "rig_deformation_claim": False,
            "notes": [
                "This is a derived delivery transform. Canonical armor geometry remains reconstructable before fitting.",
                "Only nearest-body-normal displacement is applied; topology, face order and UV indexing remain compatible.",
                "Static fit evidence must improve and real-engine silhouette must remain readable before this transform can graduate.",
            ],
        },
    }
    return output, evidence


def conform_sentinel_armor(body: Mesh, primary: Mesh, accent: Mesh):
    primary_spec = ConformSpec(clearance_min_m=0.006, clearance_max_m=0.028, strength=0.88, passes=3, max_step_m=0.042)
    accent_spec = ConformSpec(clearance_min_m=0.018, clearance_max_m=0.046, strength=0.82, passes=3, max_step_m=0.042)
    fitted_primary, primary_evidence = conform_armor_mesh(body, primary, spec=primary_spec, name=f"{primary.name}_fit_v0_1")
    fitted_accent, accent_evidence = conform_armor_mesh(body, accent, spec=accent_spec, name=f"{accent.name}_fit_v0_1")
    return fitted_primary, fitted_accent, {
        "schema": "axm.game-assets.sentinel-armor-conform.v0.1",
        "primary": primary_evidence,
        "accent": accent_evidence,
        "truth": {"production_fit_claim": False, "visual_promotion_required": True},
    }
