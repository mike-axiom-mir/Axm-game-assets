#!/usr/bin/env python3
"""Experimental attribute-aware LOD reduction for AXM character state.

Carries UVs, normals, four-slot skin influences and morph deltas through a
spatial clustering pass. It is an experimental bridge toward production LOD,
not a quality-equivalent replacement for a mature QEM/meshoptimizer reducer.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import floor, isfinite, sqrt
from typing import Sequence

from native_geometry import Mesh, Vec3, face_normal
from native_morph import MorphTarget
from native_skin import Skeleton, SkinWeights, skin_vertices, validate_skin_weights
from native_uv import UVMap, validate_uv

Vec2 = tuple[float, float]
Vec4i = tuple[int, int, int, int]
Vec4f = tuple[float, float, float, float]


@dataclass(slots=True)
class AttributeVertex:
    position: Vec3
    normal: Vec3
    uv: Vec2
    joints: Vec4i
    weights: Vec4f
    morph_deltas: list[Vec3]
    source_members: tuple[int, ...]
    material: int = 0


@dataclass(slots=True)
class AttributeMesh:
    name: str
    vertices: list[AttributeVertex]
    triangles: list[tuple[int, int, int]]
    morph_names: list[str]


def _normalize3(value: Vec3) -> Vec3:
    length = sqrt(sum(component * component for component in value))
    if length <= 1e-12:
        return (0.0, 0.0, 1.0)
    return tuple(component / length for component in value)  # type: ignore[return-value]


def _default_skin(vertex_count: int) -> SkinWeights:
    return SkinWeights([(0, 0, 0, 0)] * vertex_count, [(1.0, 0.0, 0.0, 0.0)] * vertex_count)


def from_mesh(mesh: Mesh, uvmap: UVMap, *, skin: SkinWeights | None = None, morph_targets: Sequence[MorphTarget] = ()) -> AttributeMesh:
    uv_report = validate_uv(mesh, uvmap)
    if uv_report["status"] != "pass":
        raise ValueError(f"invalid UV map: {uv_report}")
    skin = skin or _default_skin(len(mesh.vertices))
    joint_count = max((max(row) for row in skin.joints), default=0) + 1
    skin_report = validate_skin_weights(skin, vertex_count=len(mesh.vertices), joint_count=max(1, joint_count))
    if skin_report["status"] != "pass":
        raise ValueError(f"invalid skin state: {skin_report}")
    for target in morph_targets:
        if len(target.position_deltas) != len(mesh.vertices):
            raise ValueError(f"morph {target.name} does not match mesh vertex count")

    vertices: list[AttributeVertex] = []
    triangles: list[tuple[int, int, int]] = []
    source_corner = 0
    for face, uvface in zip(mesh.faces, uvmap.face_uvs):
        if len(face) < 3:
            continue
        normal = face_normal(mesh, face)
        for corner in range(1, len(face) - 1):
            tri = []
            for local in (0, corner, corner + 1):
                vi = face[local]
                ui = uvface[local]
                vertex = AttributeVertex(
                    position=mesh.vertices[vi],
                    normal=normal,
                    uv=uvmap.uvs[ui],
                    joints=skin.joints[vi],
                    weights=skin.weights[vi],
                    morph_deltas=[target.position_deltas[vi] for target in morph_targets],
                    source_members=(source_corner,),
                )
                tri.append(len(vertices))
                vertices.append(vertex)
                source_corner += 1
            triangles.append(tuple(tri))
    return AttributeMesh(mesh.name, vertices, triangles, [target.name for target in morph_targets])


def _dominant_joint(vertex: AttributeVertex) -> int:
    pairs = [(weight, joint) for joint, weight in zip(vertex.joints, vertex.weights) if weight > 0.0]
    return max(pairs, default=(1.0, 0))[1]


def _bounds(mesh: AttributeMesh) -> tuple[Vec3, Vec3]:
    xs = [v.position[0] for v in mesh.vertices]
    ys = [v.position[1] for v in mesh.vertices]
    zs = [v.position[2] for v in mesh.vertices]
    return (min(xs), min(ys), min(zs)), (max(xs), max(ys), max(zs))


def _quantize(value: float, lo: float, span: float, resolution: int) -> int:
    if span <= 1e-12:
        return 0
    t = max(0.0, min(0.999999999, (value - lo) / span))
    return int(floor(t * resolution))


def _normal_key(normal: Vec3, resolution: int = 4) -> tuple[int, int, int]:
    return tuple(max(0, min(resolution - 1, int((component * 0.5 + 0.5) * resolution))) for component in normal)  # type: ignore[return-value]


def _uv_key(uv: Vec2, resolution: int) -> tuple[int, int]:
    return (int(floor(uv[0] * resolution)), int(floor(uv[1] * resolution)))


def _merge_vertices(vertices: Sequence[AttributeVertex]) -> AttributeVertex:
    count = len(vertices)
    position = tuple(sum(v.position[axis] for v in vertices) / count for axis in range(3))
    normal = _normalize3(tuple(sum(v.normal[axis] for v in vertices) / count for axis in range(3)))
    uv = tuple(sum(v.uv[axis] for v in vertices) / count for axis in range(2))
    influence: dict[int, float] = {}
    for vertex in vertices:
        for joint, weight in zip(vertex.joints, vertex.weights):
            if weight > 0.0:
                influence[joint] = influence.get(joint, 0.0) + weight / count
    pairs = sorted(influence.items(), key=lambda item: (-item[1], item[0]))[:4]
    total = sum(weight for _, weight in pairs)
    if total <= 1e-12:
        pairs = [(0, 1.0)]
        total = 1.0
    pairs = [(joint, weight / total) for joint, weight in pairs]
    while len(pairs) < 4:
        pairs.append((0, 0.0))
    morph_count = len(vertices[0].morph_deltas)
    morph_deltas = [
        tuple(sum(vertex.morph_deltas[morph][axis] for vertex in vertices) / count for axis in range(3))
        for morph in range(morph_count)
    ]
    members = tuple(sorted(member for vertex in vertices for member in vertex.source_members))
    return AttributeVertex(
        position=position,
        normal=normal,
        uv=uv,
        joints=tuple(j for j, _ in pairs),  # type: ignore[arg-type]
        weights=tuple(w for _, w in pairs),  # type: ignore[arg-type]
        morph_deltas=morph_deltas,
        source_members=members,
        material=vertices[0].material,
    )


def simplify(mesh: AttributeMesh, *, spatial_resolution: int, uv_resolution: int = 32, normal_resolution: int = 4) -> AttributeMesh:
    if spatial_resolution < 1:
        raise ValueError("spatial_resolution must be >=1")
    if not mesh.vertices:
        return AttributeMesh(mesh.name, [], [], list(mesh.morph_names))
    lo, hi = _bounds(mesh)
    span = tuple(max(hi[i] - lo[i], 1e-12) for i in range(3))
    buckets: dict[tuple[object, ...], list[int]] = {}
    for index, vertex in enumerate(mesh.vertices):
        pos_key = tuple(_quantize(vertex.position[axis], lo[axis], span[axis], spatial_resolution) for axis in range(3))
        key = (
            *pos_key,
            *_normal_key(vertex.normal, normal_resolution),
            *_uv_key(vertex.uv, uv_resolution),
            _dominant_joint(vertex),
            vertex.material,
        )
        buckets.setdefault(key, []).append(index)

    new_vertices: list[AttributeVertex] = []
    remap: dict[int, int] = {}
    for key in sorted(buckets, key=repr):
        members = buckets[key]
        new_index = len(new_vertices)
        new_vertices.append(_merge_vertices([mesh.vertices[index] for index in members]))
        for old in members:
            remap[old] = new_index

    new_triangles: list[tuple[int, int, int]] = []
    seen: set[tuple[int, int, int]] = set()
    for triangle in mesh.triangles:
        mapped = tuple(remap[index] for index in triangle)
        if len(set(mapped)) < 3:
            continue
        canonical = tuple(sorted(mapped))
        if canonical in seen:
            continue
        seen.add(canonical)
        new_triangles.append(mapped)
    return AttributeMesh(f"{mesh.name}_attr_lod_r{spatial_resolution}", new_vertices, new_triangles, list(mesh.morph_names))


def validate(mesh: AttributeMesh, *, joint_count: int) -> dict[str, object]:
    failures: list[str] = []
    for index, vertex in enumerate(mesh.vertices):
        if not all(isfinite(value) for value in (*vertex.position, *vertex.normal, *vertex.uv, *vertex.weights)):
            failures.append(f"vertex {index} has non-finite attribute")
        if any(joint < 0 or joint >= joint_count for joint, weight in zip(vertex.joints, vertex.weights) if weight > 0.0):
            failures.append(f"vertex {index} has joint outside skeleton")
        if abs(sum(vertex.weights) - 1.0) > 1e-6:
            failures.append(f"vertex {index} weights do not sum to 1")
        if len(vertex.morph_deltas) != len(mesh.morph_names):
            failures.append(f"vertex {index} morph channel count mismatch")
    for index, triangle in enumerate(mesh.triangles):
        if len(set(triangle)) != 3 or any(vertex < 0 or vertex >= len(mesh.vertices) for vertex in triangle):
            failures.append(f"triangle {index} invalid")
    return {
        "status": "pass" if not failures else "fail",
        "failures": failures,
        "vertices": len(mesh.vertices),
        "triangles": len(mesh.triangles),
        "morph_targets": len(mesh.morph_names),
    }


def as_skin_inputs(mesh: AttributeMesh) -> tuple[Mesh, SkinWeights]:
    geometry = Mesh(mesh.name, [v.position for v in mesh.vertices], [tuple(face) for face in mesh.triangles])
    skin = SkinWeights([v.joints for v in mesh.vertices], [v.weights for v in mesh.vertices])
    return geometry, skin


def as_character_inputs(mesh: AttributeMesh) -> tuple[Mesh, UVMap, SkinWeights, list[MorphTarget]]:
    geometry, skin = as_skin_inputs(mesh)
    uvmap = UVMap([vertex.uv for vertex in mesh.vertices], [tuple(face) for face in mesh.triangles], "attribute_lod")
    morph_targets = [
        MorphTarget(name, [vertex.morph_deltas[index] for vertex in mesh.vertices])
        for index, name in enumerate(mesh.morph_names)
    ]
    return geometry, uvmap, skin, morph_targets


def deformation_error(source: AttributeMesh, simplified: AttributeMesh, bind_skeleton: Skeleton, posed_skeleton: Skeleton) -> dict[str, float]:
    source_mesh, source_skin = as_skin_inputs(source)
    lod_mesh, lod_skin = as_skin_inputs(simplified)
    source_posed = skin_vertices(source_mesh, source_skin, bind_skeleton, posed_skeleton)
    lod_posed = skin_vertices(lod_mesh, lod_skin, bind_skeleton, posed_skeleton)
    errors = []
    for lod_index, vertex in enumerate(simplified.vertices):
        members = vertex.source_members
        expected = tuple(sum(source_posed[index][axis] for index in members) / len(members) for axis in range(3))
        actual = lod_posed[lod_index]
        errors.append(sqrt(sum((actual[axis] - expected[axis]) ** 2 for axis in range(3))))
    return {
        "mean": sum(errors) / len(errors) if errors else 0.0,
        "max": max(errors, default=0.0),
    }
