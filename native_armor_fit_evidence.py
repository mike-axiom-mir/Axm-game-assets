#!/usr/bin/env python3
"""Deterministic armor-to-body proximity evidence.

This observer measures rigid armor against a canonical body without claiming a
perfect signed-distance field. It uses a deterministic spatial hash over body
vertices plus source vertex normals to estimate local clearance, likely
interpenetration, and obviously floating regions in physical meters.

The result is evidence for repair. It is not aesthetic approval and does not
turn nearest-vertex approximation into canonical geometric truth.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import floor, sqrt
from statistics import median

from native_geometry import Mesh, vertex_normals

SCHEMA = "axm.game-assets.armor-fit-evidence.v0.1"


@dataclass(frozen=True, slots=True)
class FitThresholds:
    intended_clearance_min_m: float = 0.002
    intended_clearance_max_m: float = 0.028
    likely_interpenetration_m: float = -0.003
    obvious_float_m: float = 0.050


def _dot(a, b) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _sub(a, b):
    return a[0] - b[0], a[1] - b[1], a[2] - b[2]


def _length(v) -> float:
    return sqrt(_dot(v, v))


def _percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    rows = sorted(values)
    index = min(len(rows) - 1, max(0, round((len(rows) - 1) * fraction)))
    return rows[index]


def _key(point, cell: float) -> tuple[int, int, int]:
    return tuple(int(floor(value / cell)) for value in point)


def armor_fit_evidence(
    body: Mesh,
    armor: Mesh,
    *,
    thresholds: FitThresholds = FitThresholds(),
    cell_size_m: float = 0.035,
    max_search_rings: int = 4,
) -> dict[str, object]:
    if not body.vertices or not armor.vertices:
        raise ValueError("armor fit evidence requires non-empty body and armor meshes")
    if cell_size_m <= 0.0:
        raise ValueError("cell_size_m must be positive")

    normals = vertex_normals(body)
    grid: dict[tuple[int, int, int], list[int]] = {}
    for index, point in enumerate(body.vertices):
        grid.setdefault(_key(point, cell_size_m), []).append(index)

    nearest_distances: list[float] = []
    signed_normal_offsets: list[float] = []
    fallback_queries = 0

    for point in armor.vertices:
        center = _key(point, cell_size_m)
        candidates: list[int] = []
        for ring in range(max_search_rings + 1):
            found: list[int] = []
            for dx in range(-ring, ring + 1):
                for dy in range(-ring, ring + 1):
                    for dz in range(-ring, ring + 1):
                        if ring > 0 and max(abs(dx), abs(dy), abs(dz)) != ring:
                            continue
                        found.extend(grid.get((center[0] + dx, center[1] + dy, center[2] + dz), ()))
            if found:
                candidates = found
                break
        if not candidates:
            candidates = list(range(len(body.vertices)))
            fallback_queries += 1

        nearest_index = min(candidates, key=lambda index: _length(_sub(point, body.vertices[index])))
        delta = _sub(point, body.vertices[nearest_index])
        distance = _length(delta)
        signed = _dot(delta, normals[nearest_index])
        nearest_distances.append(distance)
        signed_normal_offsets.append(signed)

    count = len(nearest_distances)
    under = sum(value < thresholds.intended_clearance_min_m for value in signed_normal_offsets)
    intended = sum(thresholds.intended_clearance_min_m <= value <= thresholds.intended_clearance_max_m for value in signed_normal_offsets)
    floaters = sum(value > thresholds.obvious_float_m for value in signed_normal_offsets)
    penetration = sum(value < thresholds.likely_interpenetration_m for value in signed_normal_offsets)
    inward = sum(value < 0.0 for value in signed_normal_offsets)

    return {
        "schema": SCHEMA,
        "sample_count": count,
        "body_vertex_count": len(body.vertices),
        "armor_vertex_count": len(armor.vertices),
        "cell_size_m": cell_size_m,
        "fallback_queries": fallback_queries,
        "nearest_distance_m": {
            "min": min(nearest_distances),
            "median": median(nearest_distances),
            "p90": _percentile(nearest_distances, 0.90),
            "p95": _percentile(nearest_distances, 0.95),
            "max": max(nearest_distances),
        },
        "signed_normal_offset_m": {
            "min": min(signed_normal_offsets),
            "median": median(signed_normal_offsets),
            "p90": _percentile(signed_normal_offsets, 0.90),
            "p95": _percentile(signed_normal_offsets, 0.95),
            "max": max(signed_normal_offsets),
        },
        "fractions": {
            "inward_of_nearest_normal": inward / count,
            "likely_interpenetrating": penetration / count,
            "under_min_clearance": under / count,
            "within_intended_clearance": intended / count,
            "obviously_floating": floaters / count,
        },
        "thresholds_m": {
            "intended_clearance_min": thresholds.intended_clearance_min_m,
            "intended_clearance_max": thresholds.intended_clearance_max_m,
            "likely_interpenetration": thresholds.likely_interpenetration_m,
            "obvious_float": thresholds.obvious_float_m,
        },
        "truth": {
            "approximation": "nearest_body_vertex_plus_body_vertex_normal",
            "production_fit_claim": False,
            "notes": [
                "This observer is deterministic proximity evidence, not an exact signed-distance field or collision solver.",
                "Large positive offsets are useful evidence for floating armor; negative offsets are useful evidence for likely penetration, but both require visual/geometry confirmation.",
                "Production armor fit should later use point-to-surface or rig-space clearance evidence under deformation as well as this static substrate check.",
            ],
        },
    }
