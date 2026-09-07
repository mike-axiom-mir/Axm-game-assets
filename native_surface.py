#!/usr/bin/env python3
"""AXM native multires organic surface kernel v0.1.

Provides dependency-free triangle subdivision, controlled smoothing, localized
brush-style deformation and deterministic normal displacement. These operations
own the geometry math but do not claim anatomy knowledge or sculpt artistry.
"""
from __future__ import annotations

from math import exp, isfinite, sqrt
from typing import Callable

from native_geometry import Mesh, Vec3, topology_report, triangulate, vertex_normals


MaskFn = Callable[[int, Vec3], float]


def _midpoint(a: Vec3, b: Vec3) -> Vec3:
    return ((a[0] + b[0]) * 0.5, (a[1] + b[1]) * 0.5, (a[2] + b[2]) * 0.5)


def subdivide(mesh: Mesh, levels: int = 1, *, name: str | None = None) -> Mesh:
    if levels < 0:
        raise ValueError("subdivision levels must be non-negative")
    current = triangulate(mesh, name=mesh.name)
    for _ in range(levels):
        vertices = list(current.vertices)
        edge_midpoints: dict[tuple[int, int], int] = {}

        def midpoint_index(a: int, b: int) -> int:
            edge = (a, b) if a < b else (b, a)
            cached = edge_midpoints.get(edge)
            if cached is not None:
                return cached
            index = len(vertices)
            vertices.append(_midpoint(current.vertices[a], current.vertices[b]))
            edge_midpoints[edge] = index
            return index

        faces = []
        for a, b, c in current.faces:
            ab = midpoint_index(a, b)
            bc = midpoint_index(b, c)
            ca = midpoint_index(c, a)
            faces.extend(((a, ab, ca), (ab, b, bc), (ca, bc, c), (ab, bc, ca)))
        current = Mesh(current.name, vertices, faces)
    if name is not None:
        current.name = name
    return current


def adjacency(mesh: Mesh) -> list[set[int]]:
    neighbors = [set() for _ in mesh.vertices]
    for face in mesh.faces:
        for index, a in enumerate(face):
            for b in face[index + 1:]:
                if a == b:
                    continue
                neighbors[a].add(b)
                neighbors[b].add(a)
    return neighbors


def boundary_vertices(mesh: Mesh) -> set[int]:
    edge_counts: dict[tuple[int, int], int] = {}
    for face in mesh.faces:
        for index, a in enumerate(face):
            b = face[(index + 1) % len(face)]
            edge = (a, b) if a < b else (b, a)
            edge_counts[edge] = edge_counts.get(edge, 0) + 1
    result: set[int] = set()
    for (a, b), count in edge_counts.items():
        if count == 1:
            result.add(a)
            result.add(b)
    return result


def smooth(mesh: Mesh, *, iterations: int = 1, strength: float = 0.25, preserve_boundary: bool = True, name: str | None = None) -> Mesh:
    if iterations < 0:
        raise ValueError("iterations must be non-negative")
    if not (0.0 <= strength <= 1.0):
        raise ValueError("smoothing strength must be within [0,1]")
    current = mesh.copy(name=name or mesh.name)
    neighbors = adjacency(current)
    boundary = boundary_vertices(current) if preserve_boundary else set()
    for _ in range(iterations):
        vertices = list(current.vertices)
        for index, point in enumerate(current.vertices):
            if index in boundary or not neighbors[index]:
                continue
            count = len(neighbors[index])
            average = tuple(sum(current.vertices[other][axis] for other in neighbors[index]) / count for axis in range(3))
            vertices[index] = tuple(point[axis] + (average[axis] - point[axis]) * strength for axis in range(3))
        current = Mesh(current.name, vertices, list(current.faces))
    return current


def gaussian_mask(center: Vec3, radius: float) -> MaskFn:
    if radius <= 0.0:
        raise ValueError("mask radius must be positive")
    inv = 1.0 / (2.0 * radius * radius)

    def mask(_: int, point: Vec3) -> float:
        distance_sq = sum((point[axis] - center[axis]) ** 2 for axis in range(3))
        return exp(-distance_sq * inv)

    return mask


def deform(mesh: Mesh, offset: Vec3, *, mask: MaskFn | None = None, name: str | None = None) -> Mesh:
    if not all(isfinite(value) for value in offset):
        raise ValueError("deformation offset must be finite")
    mask = mask or (lambda _index, _point: 1.0)
    vertices = []
    for index, point in enumerate(mesh.vertices):
        weight = float(mask(index, point))
        if not isfinite(weight):
            raise ValueError(f"mask returned non-finite weight at vertex {index}")
        weight = max(0.0, min(1.0, weight))
        vertices.append(tuple(point[axis] + offset[axis] * weight for axis in range(3)))
    return Mesh(name or mesh.name, vertices, list(mesh.faces))


def _hash_noise(index: int, seed: int) -> float:
    value = (index * 0x45D9F3B + seed * 0x27D4EB2D) & 0xFFFFFFFF
    value ^= value >> 16
    value = (value * 0x45D9F3B) & 0xFFFFFFFF
    value ^= value >> 16
    return value / 0xFFFFFFFF * 2.0 - 1.0


def normal_displace(mesh: Mesh, amplitude: float, *, seed: int = 1, mask: MaskFn | None = None, name: str | None = None) -> Mesh:
    if amplitude < 0.0 or not isfinite(amplitude):
        raise ValueError("displacement amplitude must be finite and non-negative")
    mask = mask or (lambda _index, _point: 1.0)
    normals = vertex_normals(mesh)
    vertices = []
    for index, (point, normal) in enumerate(zip(mesh.vertices, normals)):
        weight = max(0.0, min(1.0, float(mask(index, point))))
        noise = _hash_noise(index, seed)
        distance = noise * amplitude * weight
        vertices.append(tuple(point[axis] + normal[axis] * distance for axis in range(3)))
    return Mesh(name or mesh.name, vertices, list(mesh.faces))


def displacement_stats(before: Mesh, after: Mesh) -> dict[str, float]:
    if len(before.vertices) != len(after.vertices):
        raise ValueError("displacement stats require identical topology")
    distances = []
    for a, b in zip(before.vertices, after.vertices):
        distances.append(sqrt(sum((b[axis] - a[axis]) ** 2 for axis in range(3))))
    return {
        "mean": sum(distances) / len(distances) if distances else 0.0,
        "max": max(distances, default=0.0),
    }


def validate_multires(source: Mesh, result: Mesh) -> dict[str, object]:
    report = topology_report(result)
    failures = []
    if report["invalid_indices"] or report["degenerate_faces"]:
        failures.append("result contains structurally invalid geometry")
    if not result.vertices or not result.faces:
        failures.append("result is empty")
    return {
        "status": "pass" if not failures else "fail",
        "failures": failures,
        "source_vertices": len(source.vertices),
        "source_triangles": len(triangulate(source).faces),
        "result_vertices": len(result.vertices),
        "result_triangles": len(triangulate(result).faces),
        "topology": report,
    }
