#!/usr/bin/env python3
"""AXM native UV-preserving surface subdivision.

Geometry edge midpoints are shared across adjacent faces, while UV midpoint
state is keyed by UV edges so existing seams remain explicit. This is a small
native bridge between the multires geometry kernel and preserved authored UV
state; it does not claim production retopology or adaptive subdivision.
"""
from __future__ import annotations

from native_geometry import Mesh, Vec3
from native_uv import UVMap, Vec2, validate_uv


def _mid3(a: Vec3, b: Vec3) -> Vec3:
    return ((a[0] + b[0]) * 0.5, (a[1] + b[1]) * 0.5, (a[2] + b[2]) * 0.5)


def _mid2(a: Vec2, b: Vec2) -> Vec2:
    return ((a[0] + b[0]) * 0.5, (a[1] + b[1]) * 0.5)


def triangulate_with_uv(mesh: Mesh, uvmap: UVMap, *, name: str | None = None) -> tuple[Mesh, UVMap]:
    report = validate_uv(mesh, uvmap)
    if report["status"] != "pass":
        raise ValueError(f"invalid UV state before triangulation: {report}")
    faces = []
    uvfaces = []
    for face, uvface in zip(mesh.faces, uvmap.face_uvs):
        if len(face) < 3:
            continue
        if len(face) == 3:
            faces.append(tuple(face))
            uvfaces.append(tuple(uvface))
            continue
        for corner in range(1, len(face) - 1):
            faces.append((face[0], face[corner], face[corner + 1]))
            uvfaces.append((uvface[0], uvface[corner], uvface[corner + 1]))
    result_mesh = Mesh(name or mesh.name, list(mesh.vertices), faces)
    result_uv = UVMap(list(uvmap.uvs), uvfaces, f"{uvmap.method}/triangulated")
    result_report = validate_uv(result_mesh, result_uv)
    if result_report["status"] != "pass":
        raise ValueError(f"UV-aware triangulation produced invalid state: {result_report}")
    return result_mesh, result_uv


def subdivide_with_uv(
    mesh: Mesh,
    uvmap: UVMap,
    *,
    levels: int = 1,
    name: str | None = None,
) -> tuple[Mesh, UVMap]:
    if levels < 0:
        raise ValueError("subdivision levels must be non-negative")
    current_mesh, current_uv = triangulate_with_uv(mesh, uvmap, name=mesh.name)
    for level in range(levels):
        vertices = list(current_mesh.vertices)
        uvs = list(current_uv.uvs)
        geometry_midpoints: dict[tuple[int, int], int] = {}
        uv_midpoints: dict[tuple[int, int], int] = {}

        def geometry_midpoint(a: int, b: int) -> int:
            key = (a, b) if a < b else (b, a)
            if key not in geometry_midpoints:
                geometry_midpoints[key] = len(vertices)
                vertices.append(_mid3(current_mesh.vertices[a], current_mesh.vertices[b]))
            return geometry_midpoints[key]

        def uv_midpoint(a: int, b: int) -> int:
            key = (a, b) if a < b else (b, a)
            if key not in uv_midpoints:
                uv_midpoints[key] = len(uvs)
                uvs.append(_mid2(current_uv.uvs[a], current_uv.uvs[b]))
            return uv_midpoints[key]

        faces = []
        uvfaces = []
        for face, uvface in zip(current_mesh.faces, current_uv.face_uvs):
            a, b, c = face
            ua, ub, uc = uvface
            ab = geometry_midpoint(a, b)
            bc = geometry_midpoint(b, c)
            ca = geometry_midpoint(c, a)
            uab = uv_midpoint(ua, ub)
            ubc = uv_midpoint(ub, uc)
            uca = uv_midpoint(uc, ua)
            faces.extend(((a, ab, ca), (ab, b, bc), (ca, bc, c), (ab, bc, ca)))
            uvfaces.extend(((ua, uab, uca), (uab, ub, ubc), (uca, ubc, uc), (uab, ubc, uca)))
        current_mesh = Mesh(current_mesh.name, vertices, faces)
        current_uv = UVMap(uvs, uvfaces, f"{uvmap.method}/subdiv{level + 1}")
        report = validate_uv(current_mesh, current_uv)
        if report["status"] != "pass":
            raise ValueError(f"UV subdivision level {level + 1} invalid: {report}")
    if name is not None:
        current_mesh.name = name
    return current_mesh, current_uv
