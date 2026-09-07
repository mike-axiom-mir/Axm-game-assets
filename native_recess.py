#!/usr/bin/env python3
"""AXM dependency-free rectangular face-recess geometry v0.1.

Builds a closed manifold rectangular shell with one true inset cavity on the
local -Z face. This is a focused constructive primitive, not a general boolean
CSG engine.
"""
from __future__ import annotations

from math import isfinite

from native_geometry import EPS, Mesh, topology_report
from native_orientation import winding_report


def make_recessed_box(
    width: float,
    height: float,
    depth: float,
    *,
    recess_width: float,
    recess_height: float,
    recess_depth: float,
    recess_center: tuple[float, float] = (0.0, 0.0),
    name: str = "recessed_box",
) -> Mesh:
    """Create a box with a rectangular cavity inset into its local -Z face.

    The outer front/back faces are emitted as matching 3x3 grids so every edge
    introduced by the recess participates in an exact manifold topology. UVs
    and material assignment remain downstream concerns.
    """
    values = (
        width,
        height,
        depth,
        recess_width,
        recess_height,
        recess_depth,
        recess_center[0],
        recess_center[1],
    )
    if not all(isfinite(value) for value in values):
        raise ValueError("recess dimensions and center must be finite")
    if width <= EPS or height <= EPS or depth <= EPS:
        raise ValueError("outer dimensions must be positive")
    if recess_width <= EPS or recess_height <= EPS:
        raise ValueError("recess dimensions must be positive")
    if recess_depth <= EPS or recess_depth >= depth - EPS:
        raise ValueError("recess_depth must be within (0, depth)")
    if recess_width >= width - EPS or recess_height >= height - EPS:
        raise ValueError("recess must remain inside the outer face")

    sx, sy, sz = width * 0.5, height * 0.5, depth * 0.5
    cx, cy = recess_center
    rx0, rx1 = cx - recess_width * 0.5, cx + recess_width * 0.5
    ry0, ry1 = cy - recess_height * 0.5, cy + recess_height * 0.5
    if rx0 <= -sx + EPS or rx1 >= sx - EPS or ry0 <= -sy + EPS or ry1 >= sy - EPS:
        raise ValueError("recess rectangle must leave a non-zero border")

    xs = (-sx, rx0, rx1, sx)
    ys = (-sy, ry0, ry1, sy)
    z_front = -sz
    z_back = sz
    z_recess = z_front + recess_depth

    vertices: list[tuple[float, float, float]] = []
    index_by_position: dict[tuple[float, float, float], int] = {}
    faces: list[tuple[int, ...]] = []

    def vi(position: tuple[float, float, float]) -> int:
        if position not in index_by_position:
            index_by_position[position] = len(vertices)
            vertices.append(position)
        return index_by_position[position]

    def quad(*points: tuple[float, float, float]) -> None:
        faces.append(tuple(vi(point) for point in points))

    # Front (-Z): 3x3 cells with the center cell removed for the recess mouth.
    for yi in range(3):
        for xi in range(3):
            if xi == 1 and yi == 1:
                continue
            xa, xb = xs[xi], xs[xi + 1]
            ya, yb = ys[yi], ys[yi + 1]
            quad(
                (xa, ya, z_front),
                (xa, yb, z_front),
                (xb, yb, z_front),
                (xb, ya, z_front),
            )

    # Back (+Z): matching 3x3 grid preserves exact side-edge subdivisions.
    for yi in range(3):
        for xi in range(3):
            xa, xb = xs[xi], xs[xi + 1]
            ya, yb = ys[yi], ys[yi + 1]
            quad(
                (xa, ya, z_back),
                (xb, ya, z_back),
                (xb, yb, z_back),
                (xa, yb, z_back),
            )

    # Bottom/top outer faces split across X to match front/back grids.
    for xi in range(3):
        xa, xb = xs[xi], xs[xi + 1]
        quad((xa, -sy, z_front), (xb, -sy, z_front), (xb, -sy, z_back), (xa, -sy, z_back))
        quad((xb, sy, z_front), (xa, sy, z_front), (xa, sy, z_back), (xb, sy, z_back))

    # Left/right outer faces split across Y.
    for yi in range(3):
        ya, yb = ys[yi], ys[yi + 1]
        quad((-sx, yb, z_front), (-sx, ya, z_front), (-sx, ya, z_back), (-sx, yb, z_back))
        quad((sx, ya, z_front), (sx, yb, z_front), (sx, yb, z_back), (sx, ya, z_back))

    # Recess back surface faces out toward -Z into the cavity.
    quad(
        (rx0, ry0, z_recess),
        (rx0, ry1, z_recess),
        (rx1, ry1, z_recess),
        (rx1, ry0, z_recess),
    )

    # Recess walls. Normals point into the empty cavity volume.
    # Left wall +X.
    quad(
        (rx0, ry0, z_front),
        (rx0, ry1, z_front),
        (rx0, ry1, z_recess),
        (rx0, ry0, z_recess),
    )
    # Right wall -X.
    quad(
        (rx1, ry0, z_front),
        (rx1, ry0, z_recess),
        (rx1, ry1, z_recess),
        (rx1, ry1, z_front),
    )
    # Bottom wall +Y.
    quad(
        (rx0, ry0, z_front),
        (rx0, ry0, z_recess),
        (rx1, ry0, z_recess),
        (rx1, ry0, z_front),
    )
    # Top wall -Y.
    quad(
        (rx0, ry1, z_front),
        (rx1, ry1, z_front),
        (rx1, ry1, z_recess),
        (rx0, ry1, z_recess),
    )

    mesh = Mesh(name, vertices, faces)
    topology = topology_report(mesh)
    if not topology["closed_two_manifold_candidate"]:
        raise ValueError(f"recess construction produced invalid topology: {topology}")
    winding = winding_report(mesh)
    if winding["status"] != "pass":
        raise ValueError(f"recess construction produced unsafe winding: {winding}")
    return mesh


def recess_report(mesh: Mesh) -> dict[str, object]:
    topology = topology_report(mesh)
    winding = winding_report(mesh)
    return {
        "status": "pass"
        if topology["closed_two_manifold_candidate"] and winding["status"] == "pass"
        else "fail",
        "topology": topology,
        "winding": winding,
        "truth": "Focused rectangular -Z face recess. Closed/winding-safe geometry does not by itself prove bevel quality, ergonomic realism or general boolean capability.",
    }
