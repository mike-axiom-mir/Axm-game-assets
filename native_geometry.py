#!/usr/bin/env python3
"""AXM Game Asset Forge native geometry kernel v0.1.

Dependency-free geometry operations that would otherwise often be delegated to
DCC software. This is deliberately a small, inspectable kernel, not a claim to
replace Blender as a whole or to provide production retopology/sculpting.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import cos, pi, sin, sqrt
from pathlib import Path
from typing import Iterable, Sequence

Vec3 = tuple[float, float, float]
Face = tuple[int, ...]
EPS = 1e-12


@dataclass(slots=True)
class Mesh:
    name: str
    vertices: list[Vec3]
    faces: list[Face]

    def copy(self, *, name: str | None = None) -> "Mesh":
        return Mesh(name or self.name, list(self.vertices), list(self.faces))


def _sub(a: Vec3, b: Vec3) -> Vec3:
    return a[0] - b[0], a[1] - b[1], a[2] - b[2]


def _cross(a: Vec3, b: Vec3) -> Vec3:
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def _length(v: Vec3) -> float:
    return sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2])


def _normalize(v: Vec3) -> Vec3:
    length = _length(v)
    if length <= EPS:
        return 0.0, 0.0, 0.0
    return v[0] / length, v[1] / length, v[2] / length


def bounds(mesh: Mesh) -> tuple[Vec3, Vec3]:
    if not mesh.vertices:
        return (0.0, 0.0, 0.0), (0.0, 0.0, 0.0)
    xs, ys, zs = zip(*mesh.vertices)
    return (min(xs), min(ys), min(zs)), (max(xs), max(ys), max(zs))


def translate(mesh: Mesh, offset: Vec3, *, name: str | None = None) -> Mesh:
    ox, oy, oz = offset
    return Mesh(
        name or mesh.name,
        [(x + ox, y + oy, z + oz) for x, y, z in mesh.vertices],
        list(mesh.faces),
    )


def scale(mesh: Mesh, factors: Vec3 | float, *, name: str | None = None) -> Mesh:
    if isinstance(factors, (int, float)):
        sx = sy = sz = float(factors)
    else:
        sx, sy, sz = factors
    return Mesh(
        name or mesh.name,
        [(x * sx, y * sy, z * sz) for x, y, z in mesh.vertices],
        list(mesh.faces),
    )


def center_at_origin(mesh: Mesh, *, name: str | None = None) -> Mesh:
    lo, hi = bounds(mesh)
    center = tuple((a + b) * 0.5 for a, b in zip(lo, hi))
    return translate(mesh, (-center[0], -center[1], -center[2]), name=name)


def make_box(size: Vec3 = (1.0, 1.0, 1.0), *, name: str = "box") -> Mesh:
    sx, sy, sz = (v * 0.5 for v in size)
    vertices = [
        (-sx, -sy, -sz), (sx, -sy, -sz), (sx, sy, -sz), (-sx, sy, -sz),
        (-sx, -sy, sz), (sx, -sy, sz), (sx, sy, sz), (-sx, sy, sz),
    ]
    faces = [
        (0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4),
        (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7),
    ]
    return Mesh(name, vertices, faces)


def make_uv_sphere(radius: float = 1.0, *, segments: int = 32, rings: int = 16, name: str = "uv_sphere") -> Mesh:
    if segments < 3 or rings < 2:
        raise ValueError("sphere requires segments>=3 and rings>=2")
    vertices: list[Vec3] = [(0.0, radius, 0.0)]
    for ring in range(1, rings):
        phi = pi * ring / rings
        y = radius * cos(phi)
        rr = radius * sin(phi)
        for seg in range(segments):
            theta = 2.0 * pi * seg / segments
            vertices.append((rr * cos(theta), y, rr * sin(theta)))
    bottom = len(vertices)
    vertices.append((0.0, -radius, 0.0))

    faces: list[Face] = []
    first = 1
    for seg in range(segments):
        faces.append((0, first + seg, first + ((seg + 1) % segments)))
    for ring in range(rings - 2):
        row = 1 + ring * segments
        nxt = row + segments
        for seg in range(segments):
            a = row + seg
            b = row + ((seg + 1) % segments)
            c = nxt + ((seg + 1) % segments)
            d = nxt + seg
            faces.append((a, d, c, b))
    last = 1 + (rings - 2) * segments
    for seg in range(segments):
        faces.append((last + seg, bottom, last + ((seg + 1) % segments)))
    return Mesh(name, vertices, faces)


def combine(meshes: Iterable[Mesh], *, name: str = "combined") -> Mesh:
    vertices: list[Vec3] = []
    faces: list[Face] = []
    offset = 0
    for mesh in meshes:
        vertices.extend(mesh.vertices)
        faces.extend(tuple(index + offset for index in face) for face in mesh.faces)
        offset += len(mesh.vertices)
    return Mesh(name, vertices, faces)


def triangulate(mesh: Mesh, *, name: str | None = None) -> Mesh:
    triangles: list[Face] = []
    for face in mesh.faces:
        if len(face) < 3:
            continue
        if len(face) == 3:
            triangles.append(face)
            continue
        root = face[0]
        for i in range(1, len(face) - 1):
            triangles.append((root, face[i], face[i + 1]))
    return Mesh(name or mesh.name, list(mesh.vertices), triangles)


def face_normal(mesh: Mesh, face: Sequence[int]) -> Vec3:
    if len(face) < 3:
        return 0.0, 0.0, 0.0
    a, b, c = (mesh.vertices[face[i]] for i in range(3))
    return _normalize(_cross(_sub(b, a), _sub(c, a)))


def vertex_normals(mesh: Mesh) -> list[Vec3]:
    sums = [[0.0, 0.0, 0.0] for _ in mesh.vertices]
    tri = triangulate(mesh)
    for face in tri.faces:
        a, b, c = (tri.vertices[i] for i in face)
        raw = _cross(_sub(b, a), _sub(c, a))
        for index in face:
            sums[index][0] += raw[0]
            sums[index][1] += raw[1]
            sums[index][2] += raw[2]
    return [_normalize((x, y, z)) for x, y, z in sums]


def topology_report(mesh: Mesh) -> dict[str, int | bool]:
    invalid_indices = 0
    degenerate_faces = 0
    edge_counts: dict[tuple[int, int], int] = {}
    triangle_count = 0

    for face in mesh.faces:
        if len(face) < 3 or len(set(face)) < 3:
            degenerate_faces += 1
            continue
        if any(index < 0 or index >= len(mesh.vertices) for index in face):
            invalid_indices += 1
            continue
        triangle_count += max(0, len(face) - 2)
        if _length(_cross(_sub(mesh.vertices[face[1]], mesh.vertices[face[0]]), _sub(mesh.vertices[face[2]], mesh.vertices[face[0]]))) <= EPS:
            degenerate_faces += 1
        for i, a in enumerate(face):
            b = face[(i + 1) % len(face)]
            edge = (a, b) if a < b else (b, a)
            edge_counts[edge] = edge_counts.get(edge, 0) + 1

    boundary_edges = sum(count == 1 for count in edge_counts.values())
    nonmanifold_edges = sum(count > 2 for count in edge_counts.values())
    return {
        "vertices": len(mesh.vertices),
        "faces": len(mesh.faces),
        "triangles": triangle_count,
        "invalid_indices": invalid_indices,
        "degenerate_faces": degenerate_faces,
        "boundary_edges": boundary_edges,
        "nonmanifold_edges": nonmanifold_edges,
        "closed_two_manifold_candidate": bool(edge_counts) and boundary_edges == 0 and nonmanifold_edges == 0 and invalid_indices == 0 and degenerate_faces == 0,
    }


def aabb_collision(mesh: Mesh) -> dict[str, list[float] | str]:
    lo, hi = bounds(mesh)
    return {"type": "aabb", "min": list(lo), "max": list(hi)}


def _cluster(mesh: Mesh, resolution: int, *, name: str) -> Mesh:
    if resolution < 1 or not mesh.vertices:
        return mesh.copy(name=name)
    lo, hi = bounds(mesh)
    span = tuple(max(hi[i] - lo[i], EPS) for i in range(3))

    buckets: dict[tuple[int, int, int], list[int]] = {}
    for index, vertex in enumerate(mesh.vertices):
        key = []
        for axis in range(3):
            normalized = (vertex[axis] - lo[axis]) / span[axis]
            cell = min(resolution - 1, int(normalized * resolution))
            key.append(cell)
        buckets.setdefault(tuple(key), []).append(index)

    new_vertices: list[Vec3] = []
    remap: dict[int, int] = {}
    for key in sorted(buckets):
        members = buckets[key]
        centroid = tuple(sum(mesh.vertices[i][axis] for i in members) / len(members) for axis in range(3))
        new_index = len(new_vertices)
        new_vertices.append(centroid)
        for old in members:
            remap[old] = new_index

    new_faces: list[Face] = []
    seen: set[Face] = set()
    for face in triangulate(mesh).faces:
        mapped = tuple(remap[index] for index in face)
        if len(set(mapped)) < 3:
            continue
        canonical = tuple(sorted(mapped))
        if canonical in seen:
            continue
        seen.add(canonical)
        new_faces.append(mapped)
    return Mesh(name, new_vertices, new_faces)


def simplify_vertex_cluster(mesh: Mesh, target_ratio: float, *, name: str | None = None) -> Mesh:
    """Deterministic coarse LOD simplifier.

    This is intentionally a fallback, not production character retopology. It
    preserves no UV seams, skin weights, morphs or hard-edge metadata yet.
    """
    if not (0.0 < target_ratio <= 1.0):
        raise ValueError("target_ratio must be within (0, 1]")
    tri = triangulate(mesh)
    if target_ratio >= 0.999 or len(tri.vertices) < 8:
        return tri.copy(name=name or f"{mesh.name}_lod")
    target_vertices = max(4, int(len(tri.vertices) * target_ratio))
    initial = max(1, round(target_vertices ** (1.0 / 3.0)))
    best = tri
    for resolution in range(max(1, initial - 2), initial + 4):
        candidate = _cluster(tri, resolution, name=name or f"{mesh.name}_lod")
        if len(candidate.vertices) <= len(best.vertices):
            best = candidate
        if len(candidate.vertices) <= target_vertices:
            best = candidate
            break
    return best


def lod_chain(mesh: Mesh, ratios: Sequence[float] = (1.0, 0.55, 0.28, 0.14)) -> list[Mesh]:
    chain: list[Mesh] = []
    previous = triangulate(mesh, name=f"{mesh.name}_lod0")
    chain.append(previous)
    for index, ratio in enumerate(ratios[1:], 1):
        candidate = simplify_vertex_cluster(mesh, ratio, name=f"{mesh.name}_lod{index}")
        if len(candidate.faces) >= len(previous.faces):
            pressure = ratio * 0.8
            for _ in range(6):
                candidate = simplify_vertex_cluster(mesh, max(0.01, pressure), name=f"{mesh.name}_lod{index}")
                if len(candidate.faces) < len(previous.faces):
                    break
                pressure *= 0.7
        chain.append(candidate)
        previous = candidate
    return chain


def write_obj(mesh: Mesh, path: str | Path, *, include_normals: bool = True) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"o {mesh.name}"]
    for x, y, z in mesh.vertices:
        lines.append(f"v {x:.9g} {y:.9g} {z:.9g}")
    normals = vertex_normals(mesh) if include_normals else []
    for x, y, z in normals:
        lines.append(f"vn {x:.9g} {y:.9g} {z:.9g}")
    for face in mesh.faces:
        if include_normals:
            lines.append("f " + " ".join(f"{i + 1}//{i + 1}" for i in face))
        else:
            lines.append("f " + " ".join(str(i + 1) for i in face))
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")


def read_obj(path: str | Path, *, name: str | None = None) -> Mesh:
    vertices: list[Vec3] = []
    faces: list[Face] = []
    object_name = name or Path(path).stem
    for raw in Path(path).read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if parts[0] == "o" and len(parts) > 1 and name is None:
            object_name = "_".join(parts[1:])
        elif parts[0] == "v" and len(parts) >= 4:
            vertices.append((float(parts[1]), float(parts[2]), float(parts[3])))
        elif parts[0] == "f" and len(parts) >= 4:
            face: list[int] = []
            for token in parts[1:]:
                raw_index = token.split("/", 1)[0]
                index = int(raw_index)
                if index < 0:
                    index = len(vertices) + index
                else:
                    index -= 1
                face.append(index)
            faces.append(tuple(face))
    return Mesh(object_name, vertices, faces)
