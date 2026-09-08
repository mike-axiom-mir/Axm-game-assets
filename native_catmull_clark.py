#!/usr/bin/env python3
"""Controlled Catmull-Clark-style subdivision with face-varying UV preservation.

Designed for authored quad-dominant surfaces such as the hm08 human topology.
Geometry uses standard Catmull-Clark face/edge/vertex rules with an explicit
shape-strength blend back toward the source surface. Open boundaries use the
standard cubic boundary rule when two boundary neighbors are available.

UVs remain face-varying: original UV coordinates are preserved, new edge UVs
are midpoints keyed by UV edges, and new face UVs are per-face averages. That
retains existing seams instead of welding islands together.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from native_geometry import Mesh, Vec3
from native_uv import UVMap, Vec2, validate_uv


def _avg3(values: list[Vec3]) -> Vec3:
    count = len(values)
    return tuple(sum(value[axis] for value in values) / count for axis in range(3))  # type: ignore[return-value]


def _avg2(values: list[Vec2]) -> Vec2:
    count = len(values)
    return tuple(sum(value[axis] for value in values) / count for axis in range(2))  # type: ignore[return-value]


def _mid3(a: Vec3, b: Vec3) -> Vec3:
    return ((a[0]+b[0])*0.5,(a[1]+b[1])*0.5,(a[2]+b[2])*0.5)


def _mid2(a: Vec2, b: Vec2) -> Vec2:
    return ((a[0]+b[0])*0.5,(a[1]+b[1])*0.5)


def _lerp3(a: Vec3, b: Vec3, t: float) -> Vec3:
    return tuple(a[axis] + (b[axis]-a[axis])*t for axis in range(3))  # type: ignore[return-value]


def catmull_clark_with_uv(
    mesh: Mesh,
    uvmap: UVMap,
    *,
    levels: int = 1,
    shape_strength: float = 0.5,
    name: str | None = None,
) -> tuple[Mesh, UVMap]:
    if levels < 0:
        raise ValueError("Catmull-Clark levels must be non-negative")
    if not (0.0 <= shape_strength <= 1.0):
        raise ValueError("shape_strength must be within [0,1]")
    report = validate_uv(mesh, uvmap)
    if report["status"] != "pass":
        raise ValueError(f"invalid UV state before Catmull-Clark: {report}")

    current_mesh = mesh.copy(name=name or mesh.name)
    current_uv = UVMap(list(uvmap.uvs), list(uvmap.face_uvs), uvmap.method)

    for level in range(levels):
        # Geometry face points and topology incidence.
        face_points = [_avg3([current_mesh.vertices[index] for index in face]) for face in current_mesh.faces]
        edge_faces: dict[tuple[int,int], list[int]] = defaultdict(list)
        vertex_faces: dict[int, list[int]] = defaultdict(list)
        vertex_edges: dict[int, set[tuple[int,int]]] = defaultdict(set)
        for face_index, face in enumerate(current_mesh.faces):
            for vertex in face:
                vertex_faces[vertex].append(face_index)
            for i, a in enumerate(face):
                b = face[(i+1)%len(face)]
                edge = (a,b) if a < b else (b,a)
                edge_faces[edge].append(face_index)
                vertex_edges[a].add(edge)
                vertex_edges[b].add(edge)

        boundary_neighbors: dict[int, set[int]] = defaultdict(set)
        for edge, incident in edge_faces.items():
            if len(incident) == 1:
                a,b = edge
                boundary_neighbors[a].add(b)
                boundary_neighbors[b].add(a)

        # Reposition original vertices, preserving indices.
        new_vertices: list[Vec3] = []
        for index, point in enumerate(current_mesh.vertices):
            bneighbors = sorted(boundary_neighbors.get(index, set()))
            if len(bneighbors) == 2:
                p1 = current_mesh.vertices[bneighbors[0]]
                p2 = current_mesh.vertices[bneighbors[1]]
                cc = tuple((6.0*point[axis] + p1[axis] + p2[axis]) / 8.0 for axis in range(3))
            elif bneighbors:
                # Non-regular open boundary: preserve source truth rather than
                # inventing an aggressive smoothing rule.
                cc = point
            else:
                faces = vertex_faces.get(index, [])
                edges = vertex_edges.get(index, set())
                n = len(faces)
                if n == 0 or len(edges) == 0:
                    cc = point
                else:
                    f = _avg3([face_points[face] for face in faces])
                    r = _avg3([_mid3(current_mesh.vertices[a], current_mesh.vertices[b]) for a,b in edges])
                    cc = tuple((f[axis] + 2.0*r[axis] + (n-3.0)*point[axis]) / n for axis in range(3))
            new_vertices.append(_lerp3(point, cc, shape_strength))

        edge_point_index: dict[tuple[int,int], int] = {}
        for edge in sorted(edge_faces):
            a,b = edge
            midpoint = _mid3(current_mesh.vertices[a], current_mesh.vertices[b])
            incident = edge_faces[edge]
            if len(incident) == 2:
                full = tuple((current_mesh.vertices[a][axis] + current_mesh.vertices[b][axis] + face_points[incident[0]][axis] + face_points[incident[1]][axis]) / 4.0 for axis in range(3))
                point = _lerp3(midpoint, full, shape_strength)
            else:
                point = midpoint
            edge_point_index[edge] = len(new_vertices)
            new_vertices.append(point)

        face_point_index: list[int] = []
        for point in face_points:
            face_point_index.append(len(new_vertices))
            new_vertices.append(point)

        # UV face-varying state. Preserve all original UVs exactly.
        new_uvs = list(current_uv.uvs)
        uv_edge_point_index: dict[tuple[int,int], int] = {}
        uv_face_point_index: list[int] = []
        for uvface in current_uv.face_uvs:
            uv_face_point_index.append(len(new_uvs))
            new_uvs.append(_avg2([current_uv.uvs[index] for index in uvface]))

        def uv_edge_point(a: int, b: int) -> int:
            key = (a,b) if a < b else (b,a)
            if key not in uv_edge_point_index:
                uv_edge_point_index[key] = len(new_uvs)
                new_uvs.append(_mid2(current_uv.uvs[a], current_uv.uvs[b]))
            return uv_edge_point_index[key]

        new_faces = []
        new_uv_faces = []
        for face_index, (face, uvface) in enumerate(zip(current_mesh.faces, current_uv.face_uvs)):
            count = len(face)
            for corner in range(count):
                vertex = face[corner]
                next_vertex = face[(corner+1)%count]
                prev_vertex = face[(corner-1)%count]
                uv = uvface[corner]
                next_uv = uvface[(corner+1)%count]
                prev_uv = uvface[(corner-1)%count]
                edge_next = (vertex,next_vertex) if vertex < next_vertex else (next_vertex,vertex)
                edge_prev = (prev_vertex,vertex) if prev_vertex < vertex else (vertex,prev_vertex)
                new_faces.append((vertex, edge_point_index[edge_next], face_point_index[face_index], edge_point_index[edge_prev]))
                new_uv_faces.append((uv, uv_edge_point(uv,next_uv), uv_face_point_index[face_index], uv_edge_point(prev_uv,uv)))

        current_mesh = Mesh(current_mesh.name, new_vertices, new_faces)
        current_uv = UVMap(new_uvs, new_uv_faces, f"{uvmap.method}/catmull-clark{level+1}:strength={shape_strength:.4g}")
        result_report = validate_uv(current_mesh, current_uv)
        if result_report["status"] != "pass":
            raise ValueError(f"Catmull-Clark UV state invalid at level {level+1}: {result_report}")

    if name is not None:
        current_mesh.name = name
    return current_mesh, current_uv
