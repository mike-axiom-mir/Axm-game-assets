#!/usr/bin/env python3
"""Deterministic layered hard-surface detail proof for Sentinel armor."""
from __future__ import annotations

from dataclasses import dataclass

from native_geometry import Mesh, bounds, combine, topology_report, triangulate
from native_modeling import make_chamfered_box, make_cylinder, place


@dataclass(frozen=True, slots=True)
class DetailReport:
    level: int
    components: int
    semantic_features: tuple[str, ...]
    vertices: int
    triangles: int
    bounds: tuple[tuple[float, float, float], tuple[float, float, float]]


def sentinel_armor_plate(level: int = 3) -> tuple[Mesh, DetailReport]:
    if level < 0 or level > 3:
        raise ValueError("detail level must be 0..3")
    parts: list[Mesh] = []
    features: list[str] = ["chamfered_primary_plate"]
    base = make_chamfered_box(0.56, 0.72, 0.075, 0.055, name="primary_plate")
    parts.append(base)

    if level >= 1:
        parts.append(place(make_chamfered_box(0.34, 0.42, 0.026, 0.035, name="raised_core"), z=0.0505))
        parts.append(place(make_chamfered_box(0.052, 0.50, 0.020, 0.012, name="left_rail"), x=-0.228, z=0.0475))
        parts.append(place(make_chamfered_box(0.052, 0.50, 0.020, 0.012, name="right_rail"), x=0.228, z=0.0475))
        features.extend(["raised_core", "edge_rails"])

    if level >= 2:
        for x in (-0.205, 0.205):
            for y in (-0.27, 0.27):
                parts.append(place(make_cylinder(0.018, 0.018, segments=12, name="fastener"), x=x, y=y, z=0.047))
        for index in range(5):
            y = 0.105 + index * 0.035
            parts.append(place(make_chamfered_box(0.18, 0.014, 0.014, 0.004, name="vent_slit"), y=y, z=0.056))
        features.extend(["corner_fasteners", "vent_array"])

    if level >= 3:
        for y in (-0.145, -0.095, -0.045):
            parts.append(place(make_chamfered_box(0.12, 0.022, 0.012, 0.004, name="service_rib"), y=y, z=0.063))
        for x in (-0.105, 0.105):
            parts.append(place(make_cylinder(0.028, 0.016, segments=16, name="biomech_port"), x=x, y=-0.215, z=0.057))
            parts.append(place(make_cylinder(0.010, 0.020, segments=10, name="micro_fastener"), x=x, y=-0.165, z=0.060))
        parts.append(place(make_chamfered_box(0.026, 0.24, 0.018, 0.006, name="spine_channel"), y=-0.02, z=0.061))
        features.extend(["service_ribs", "biomech_ports", "micro_fasteners", "spine_channel"])

    mesh = combine(parts, name=f"sentinel_armor_detail_l{level}")
    tri = triangulate(mesh)
    report = DetailReport(
        level=level,
        components=len(parts),
        semantic_features=tuple(features),
        vertices=len(mesh.vertices),
        triangles=len(tri.faces),
        bounds=bounds(mesh),
    )
    return mesh, report


def detail_progression() -> list[DetailReport]:
    return [sentinel_armor_plate(level)[1] for level in range(4)]


def validate_detail_progression() -> dict[str, object]:
    reports = detail_progression()
    failures = []
    triangles = [report.triangles for report in reports]
    components = [report.components for report in reports]
    if not all(b > a for a, b in zip(triangles, triangles[1:])):
        failures.append("triangle detail must increase monotonically")
    if not all(b > a for a, b in zip(components, components[1:])):
        failures.append("component detail must increase monotonically")
    for level in range(4):
        mesh, _ = sentinel_armor_plate(level)
        if not topology_report(mesh)["closed_two_manifold_candidate"]:
            failures.append(f"level {level} contains an open/non-manifold component shell")
    return {
        "status": "pass" if not failures else "fail",
        "failures": failures,
        "levels": [{
            "level": report.level,
            "components": report.components,
            "semantic_features": list(report.semantic_features),
            "vertices": report.vertices,
            "triangles": report.triangles,
            "bounds": report.bounds,
        } for report in reports],
    }
