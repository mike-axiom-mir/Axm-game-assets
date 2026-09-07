#!/usr/bin/env python3
"""AXM native layered eye geometry v0.1."""
from __future__ import annotations

from dataclasses import dataclass
from math import pi, cos, sin

from native_geometry import Mesh, combine, make_uv_sphere, scale, topology_report
from native_modeling import make_cylinder, place


@dataclass(slots=True)
class EyeAssembly:
    components: dict[str, Mesh]
    radius_m: float
    forward_axis: str = "+Z"


def make_cornea_dome(radius: float, height: float, *, segments: int = 32, rings: int = 6, name: str = "cornea") -> Mesh:
    if radius <= 0.0 or height <= 0.0:
        raise ValueError("cornea radius/height must be positive")
    if segments < 8 or rings < 2:
        raise ValueError("cornea dome needs segments>=8 and rings>=2")
    vertices = [(0.0, 0.0, height)]
    for ring in range(1, rings + 1):
        t = ring / rings
        rr = radius * t
        z = height * (1.0 - t * t)
        for segment in range(segments):
            angle = 2.0 * pi * segment / segments
            vertices.append((rr * cos(angle), rr * sin(angle), z))
    back_center = len(vertices)
    vertices.append((0.0, 0.0, 0.0))
    faces = []
    first = 1
    for segment in range(segments):
        faces.append((0, first + segment, first + ((segment + 1) % segments)))
    for ring in range(rings - 1):
        row = 1 + ring * segments
        nxt = row + segments
        for segment in range(segments):
            a = row + segment
            b = row + ((segment + 1) % segments)
            c = nxt + ((segment + 1) % segments)
            d = nxt + segment
            faces.append((a, d, c, b))
    last = 1 + (rings - 1) * segments
    for segment in range(segments):
        faces.append((last + segment, back_center, last + ((segment + 1) % segments)))
    return Mesh(name, vertices, faces)


def make_eye(radius_m: float = 0.012, *, name: str = "eye") -> EyeAssembly:
    if radius_m <= 0.0:
        raise ValueError("eye radius must be positive")
    sclera = make_uv_sphere(radius_m, segments=32, rings=16, name=f"{name}_sclera")
    iris_radius = radius_m * 0.46
    iris = place(
        make_cylinder(iris_radius, radius_m * 0.028, segments=48, name=f"{name}_iris"),
        z=radius_m * 0.982,
    )
    pupil = place(
        make_cylinder(radius_m * 0.19, radius_m * 0.032, segments=40, name=f"{name}_pupil"),
        z=radius_m * 0.997,
    )
    cornea = place(
        make_cornea_dome(radius_m * 0.56, radius_m * 0.16, segments=40, rings=8, name=f"{name}_cornea"),
        z=radius_m * 0.985,
    )
    return EyeAssembly({"sclera": sclera, "iris": iris, "pupil": pupil, "cornea": cornea}, radius_m)


def combined_eye(assembly: EyeAssembly, *, name: str = "eye_combined") -> Mesh:
    return combine([assembly.components[key] for key in ("sclera", "iris", "pupil", "cornea")], name=name)


def validate_eye(assembly: EyeAssembly) -> dict[str, object]:
    failures = []
    reports = {}
    for name, mesh in assembly.components.items():
        report = topology_report(mesh)
        reports[name] = report
        if not report["closed_two_manifold_candidate"]:
            failures.append(f"component {name} is not a closed two-manifold candidate")
    if set(assembly.components) != {"sclera", "iris", "pupil", "cornea"}:
        failures.append("eye must preserve sclera/iris/pupil/cornea components")
    return {
        "status": "pass" if not failures else "fail",
        "failures": failures,
        "radius_m": assembly.radius_m,
        "components": reports,
        "truth": "Layered geometric eye structure; optical/material quality is validated separately.",
    }
