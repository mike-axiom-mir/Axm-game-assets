#!/usr/bin/env python3
"""AXM dependency-free constructive modeling primitives v0.1."""
from __future__ import annotations

from math import cos, pi, sin
from typing import Sequence

from native_geometry import Mesh, translate

Vec2 = tuple[float, float]


def extrude_polygon(points: Sequence[Vec2], depth: float, *, name: str = "extrusion") -> Mesh:
    if len(points) < 3:
        raise ValueError("extrusion needs at least three profile points")
    if depth <= 0.0:
        raise ValueError("extrusion depth must be positive")
    half = depth * 0.5
    vertices = [(float(x), float(y), -half) for x, y in points] + [(float(x), float(y), half) for x, y in points]
    count = len(points)
    faces = [tuple(reversed(range(count))), tuple(range(count, count * 2))]
    for index in range(count):
        nxt = (index + 1) % count
        faces.append((index, nxt, count + nxt, count + index))
    return Mesh(name, vertices, faces)


def chamfered_rectangle(width: float, height: float, chamfer: float) -> list[Vec2]:
    if width <= 0.0 or height <= 0.0:
        raise ValueError("rectangle dimensions must be positive")
    limit = min(width, height) * 0.5
    if not (0.0 <= chamfer < limit):
        raise ValueError("chamfer must be >=0 and less than half the smaller dimension")
    x, y = width * 0.5, height * 0.5
    c = chamfer
    if c <= 1e-12:
        return [(-x, -y), (x, -y), (x, y), (-x, y)]
    return [
        (-x + c, -y), (x - c, -y), (x, -y + c), (x, y - c),
        (x - c, y), (-x + c, y), (-x, y - c), (-x, -y + c),
    ]


def make_chamfered_box(width: float, height: float, depth: float, chamfer: float, *, name: str = "chamfered_box") -> Mesh:
    return extrude_polygon(chamfered_rectangle(width, height, chamfer), depth, name=name)


def make_cylinder(radius: float, depth: float, *, segments: int = 16, name: str = "cylinder") -> Mesh:
    if radius <= 0.0:
        raise ValueError("cylinder radius must be positive")
    if segments < 3:
        raise ValueError("cylinder needs >=3 segments")
    points = [(radius * cos(2.0 * pi * i / segments), radius * sin(2.0 * pi * i / segments)) for i in range(segments)]
    return extrude_polygon(points, depth, name=name)


def place(mesh: Mesh, x: float = 0.0, y: float = 0.0, z: float = 0.0, *, name: str | None = None) -> Mesh:
    return translate(mesh, (x, y, z), name=name)
