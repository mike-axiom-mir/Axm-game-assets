#!/usr/bin/env python3
"""AXM Game Asset Forge native UV channel state and OBJ UV interchange."""
from __future__ import annotations

from dataclasses import dataclass
from math import asin, atan2, isfinite, pi, sqrt
from pathlib import Path

from native_geometry import EPS, Face, Mesh, Vec3, bounds, face_normal, vertex_normals

Vec2 = tuple[float, float]


@dataclass(slots=True)
class UVMap:
    uvs: list[Vec2]
    face_uvs: list[Face]
    method: str


def _safe_span(value: float) -> float:
    return value if abs(value) > EPS else 1.0


def box_project(mesh: Mesh) -> UVMap:
    """Per-face normalized box projection with explicit seams.

    This legacy/native fallback deliberately normalizes the whole mesh bounds to
    0..1. It is useful for self-contained fixtures but does not preserve a
    physical texel scale across differently sized meshes or material groups.
    Use ``box_project_world`` when stable world-space surface scale matters.
    """
    lo, hi = bounds(mesh)
    sx, sy, sz = (_safe_span(hi[i] - lo[i]) for i in range(3))
    uvs: list[Vec2] = []
    face_uvs: list[Face] = []
    for face in mesh.faces:
        nx, ny, nz = face_normal(mesh, face)
        axis = max(range(3), key=lambda i: abs((nx, ny, nz)[i]))
        refs: list[int] = []
        for vertex_index in face:
            x, y, z = mesh.vertices[vertex_index]
            if axis == 0:
                u, v = (z - lo[2]) / sz, (y - lo[1]) / sy
                if nx < 0:
                    u = 1.0 - u
            elif axis == 1:
                u, v = (x - lo[0]) / sx, (z - lo[2]) / sz
                if ny < 0:
                    v = 1.0 - v
            else:
                u, v = (x - lo[0]) / sx, (y - lo[1]) / sy
                if nz < 0:
                    u = 1.0 - u
            refs.append(len(uvs))
            uvs.append((u, v))
        face_uvs.append(tuple(refs))
    return UVMap(uvs, face_uvs, "box_projection")


def box_project_world(
    mesh: Mesh,
    *,
    world_units_per_tile: float = 0.20,
    origin: Vec3 = (0.0, 0.0, 0.0),
) -> UVMap:
    """Per-face box projection with a stable physical/world-space tile scale.

    Unlike :func:`box_project`, coordinates are not normalized to the mesh or
    material-group bounds. A single UV unit represents ``world_units_per_tile``
    in canonical mesh space. UVs may therefore lie outside 0..1; glTF's repeat
    sampler intentionally tiles the deterministic source map.

    This is a texel-scale mechanism, not an atlas/packing claim. It preserves
    repeat scale across separately compiled material groups and differently
    sized rigid meshes, but seams/orientation still require visual gates.
    """
    if not isfinite(world_units_per_tile) or world_units_per_tile <= EPS:
        raise ValueError("world_units_per_tile must be finite and positive")
    if len(origin) != 3 or not all(isfinite(value) for value in origin):
        raise ValueError("world projection origin must contain three finite values")

    scale = 1.0 / world_units_per_tile
    ox, oy, oz = origin
    uvs: list[Vec2] = []
    face_uvs: list[Face] = []
    for face in mesh.faces:
        nx, ny, nz = face_normal(mesh, face)
        axis = max(range(3), key=lambda i: abs((nx, ny, nz)[i]))
        refs: list[int] = []
        for vertex_index in face:
            x, y, z = mesh.vertices[vertex_index]
            if axis == 0:
                u, v = (z - oz) * scale, (y - oy) * scale
                if nx < 0:
                    u = -u
            elif axis == 1:
                u, v = (x - ox) * scale, (z - oz) * scale
                if ny < 0:
                    v = -v
            else:
                u, v = (x - ox) * scale, (y - oy) * scale
                if nz < 0:
                    u = -u
            refs.append(len(uvs))
            uvs.append((u, v))
        face_uvs.append(tuple(refs))
    return UVMap(
        uvs,
        face_uvs,
        f"box_projection_world:{world_units_per_tile:.9g}",
    )


def spherical_project(mesh: Mesh) -> UVMap:
    """Spherical projection with per-face seam unwrapping."""
    uvs: list[Vec2] = []
    face_uvs: list[Face] = []
    for face in mesh.faces:
        projected: list[Vec2] = []
        for vertex_index in face:
            x, y, z = mesh.vertices[vertex_index]
            length = sqrt(x * x + y * y + z * z)
            if length <= EPS:
                projected.append((0.5, 0.5))
                continue
            u = atan2(z, x) / (2.0 * pi) + 0.5
            v = asin(max(-1.0, min(1.0, y / length))) / pi + 0.5
            projected.append((u, v))
        if projected and max(u for u, _ in projected) - min(u for u, _ in projected) > 0.5:
            projected = [(u + 1.0 if u < 0.5 else u, v) for u, v in projected]
        refs: list[int] = []
        for uv in projected:
            refs.append(len(uvs))
            uvs.append(uv)
        face_uvs.append(tuple(refs))
    return UVMap(uvs, face_uvs, "spherical_projection")


def validate_uv(mesh: Mesh, uvmap: UVMap) -> dict[str, int | bool | str]:
    bad_face_count = int(len(mesh.faces) != len(uvmap.face_uvs))
    bad_corner_counts = 0
    bad_indices = 0
    non_finite = 0
    for face_index, face in enumerate(mesh.faces):
        if face_index >= len(uvmap.face_uvs):
            bad_corner_counts += 1
            continue
        uvface = uvmap.face_uvs[face_index]
        if len(face) != len(uvface):
            bad_corner_counts += 1
        for index in uvface:
            if index < 0 or index >= len(uvmap.uvs):
                bad_indices += 1
                continue
            u, v = uvmap.uvs[index]
            if not (isfinite(u) and isfinite(v)):
                non_finite += 1
    ok = not (bad_face_count or bad_corner_counts or bad_indices or non_finite)
    return {
        "status": "pass" if ok else "fail",
        "method": uvmap.method,
        "uvs": len(uvmap.uvs),
        "bad_face_count": bad_face_count,
        "bad_corner_counts": bad_corner_counts,
        "bad_indices": bad_indices,
        "non_finite": non_finite,
    }


def write_obj_uv(mesh: Mesh, uvmap: UVMap, path: str | Path, *, material: str | None = None) -> None:
    report = validate_uv(mesh, uvmap)
    if report["status"] != "pass":
        raise ValueError(f"invalid UV map: {report}")
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"o {mesh.name}"]
    if material:
        lines.append(f"usemtl {material}")
    for x, y, z in mesh.vertices:
        lines.append(f"v {x:.9g} {y:.9g} {z:.9g}")
    for u, v in uvmap.uvs:
        lines.append(f"vt {u:.9g} {v:.9g}")
    normals = vertex_normals(mesh)
    for x, y, z in normals:
        lines.append(f"vn {x:.9g} {y:.9g} {z:.9g}")
    for face, uvface in zip(mesh.faces, uvmap.face_uvs):
        tokens = [f"{vi + 1}/{ui + 1}/{vi + 1}" for vi, ui in zip(face, uvface)]
        lines.append("f " + " ".join(tokens))
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")


def read_obj_uv(path: str | Path, *, name: str | None = None) -> tuple[Mesh, UVMap]:
    vertices: list[Vec3] = []
    faces: list[Face] = []
    uvs: list[Vec2] = []
    face_uvs: list[Face] = []
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
        elif parts[0] == "vt" and len(parts) >= 3:
            uvs.append((float(parts[1]), float(parts[2])))
        elif parts[0] == "f" and len(parts) >= 4:
            face: list[int] = []
            uvface: list[int] = []
            for token in parts[1:]:
                values = token.split("/")
                vi = int(values[0])
                vi = len(vertices) + vi if vi < 0 else vi - 1
                face.append(vi)
                if len(values) > 1 and values[1]:
                    ui = int(values[1])
                    ui = len(uvs) + ui if ui < 0 else ui - 1
                    uvface.append(ui)
            faces.append(tuple(face))
            face_uvs.append(tuple(uvface))
    mesh = Mesh(object_name, vertices, faces)
    uvmap = UVMap(uvs, face_uvs, "obj_import")
    return mesh, uvmap
