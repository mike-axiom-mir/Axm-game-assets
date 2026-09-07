#!/usr/bin/env python3
"""AXM closed-mesh winding/orientation evidence v0.1."""
from __future__ import annotations

from math import sqrt

from native_geometry import Mesh, triangulate, topology_report


def signed_volume(mesh: Mesh) -> float:
    """Return origin-independent signed volume for a closed oriented triangle mesh.

    Positive volume corresponds to the winding convention used by AXM native
    primitives. Negative volume indicates globally reversed winding. Open or
    self-intersecting meshes can produce ambiguous values and must not use this
    as their only validity gate.
    """
    total = 0.0
    tri = triangulate(mesh)
    for ia, ib, ic in tri.faces:
        ax, ay, az = tri.vertices[ia]
        bx, by, bz = tri.vertices[ib]
        cx, cy, cz = tri.vertices[ic]
        total += (
            ax * (by * cz - bz * cy)
            + ay * (bz * cx - bx * cz)
            + az * (bx * cy - by * cx)
        ) / 6.0
    return total


def surface_area(mesh: Mesh) -> float:
    total = 0.0
    tri = triangulate(mesh)
    for ia, ib, ic in tri.faces:
        a, b, c = tri.vertices[ia], tri.vertices[ib], tri.vertices[ic]
        ab = (b[0] - a[0], b[1] - a[1], b[2] - a[2])
        ac = (c[0] - a[0], c[1] - a[1], c[2] - a[2])
        cross = (
            ab[1] * ac[2] - ab[2] * ac[1],
            ab[2] * ac[0] - ab[0] * ac[2],
            ab[0] * ac[1] - ab[1] * ac[0],
        )
        total += 0.5 * sqrt(cross[0] * cross[0] + cross[1] * cross[1] + cross[2] * cross[2])
    return total


def winding_report(mesh: Mesh, *, epsilon: float = 1e-12) -> dict[str, object]:
    topology = topology_report(mesh)
    volume = signed_volume(mesh)
    area = surface_area(mesh)
    closed = bool(topology["closed_two_manifold_candidate"])
    if not closed:
        classification = "open_or_nonmanifold"
    elif volume > epsilon:
        classification = "outward"
    elif volume < -epsilon:
        classification = "inward"
    else:
        classification = "degenerate_or_ambiguous"
    return {
        "status": "pass" if classification == "outward" else "fail",
        "classification": classification,
        "signed_volume": volume,
        "absolute_volume": abs(volume),
        "surface_area": area,
        "topology": topology,
        "truth": "Signed volume is a winding diagnostic for closed oriented shells. Open/self-intersecting geometry requires different evidence.",
    }


def reverse_winding(mesh: Mesh, *, name: str | None = None) -> Mesh:
    return Mesh(name or mesh.name, list(mesh.vertices), [tuple(reversed(face)) for face in mesh.faces])


def orient_outward(mesh: Mesh, *, name: str | None = None) -> Mesh:
    report = winding_report(mesh)
    if report["classification"] == "outward":
        return mesh.copy(name=name or mesh.name)
    if report["classification"] == "inward":
        return reverse_winding(mesh, name=name or mesh.name)
    raise ValueError(f"cannot safely orient mesh classified as {report['classification']}")
