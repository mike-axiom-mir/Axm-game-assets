#!/usr/bin/env python3
"""AXM native guide-curve and hair-card state v0.2."""
from __future__ import annotations

import random
from dataclasses import dataclass
from math import isfinite, sqrt

from native_geometry import Mesh, Vec3, bounds, combine, vertex_normals
from native_uv import UVMap


@dataclass(slots=True)
class HairGuide:
    points: list[Vec3]
    root_normal: Vec3
    root_width: float
    tip_width: float
    group: str = "scalp"


@dataclass(slots=True)
class HairSystem:
    guides: list[HairGuide]
    seed: int
    style: str


def _add(a: Vec3, b: Vec3) -> Vec3:
    return a[0] + b[0], a[1] + b[1], a[2] + b[2]


def _sub(a: Vec3, b: Vec3) -> Vec3:
    return a[0] - b[0], a[1] - b[1], a[2] - b[2]


def _mul(v: Vec3, scalar: float) -> Vec3:
    return v[0] * scalar, v[1] * scalar, v[2] * scalar


def _cross(a: Vec3, b: Vec3) -> Vec3:
    return a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]


def _normalize(v: Vec3) -> Vec3:
    length = sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2])
    if length <= 1e-12:
        return 0.0, 1.0, 0.0
    return v[0] / length, v[1] / length, v[2] / length


def _fallback_side(tangent: Vec3) -> Vec3:
    axis = (0.0, 1.0, 0.0) if abs(tangent[1]) < 0.9 else (1.0, 0.0, 0.0)
    return _normalize(_cross(tangent, axis))


def generate_short_hair(
    head: Mesh,
    *,
    guide_count: int = 64,
    segments: int = 5,
    length: float = 0.035,
    root_width: float = 0.0045,
    tip_width: float = 0.0008,
    seed: int = 1,
) -> HairSystem:
    if guide_count < 1 or segments < 2:
        raise ValueError("hair needs guide_count>=1 and segments>=2")
    if length <= 0.0 or root_width <= 0.0 or tip_width < 0.0 or tip_width > root_width:
        raise ValueError("invalid hair dimensions")
    lo, hi = bounds(head)
    span_y = max(hi[1] - lo[1], 1e-9)
    span_z = max(hi[2] - lo[2], 1e-9)
    normals = vertex_normals(head)
    candidates = [
        index for index, point in enumerate(head.vertices)
        if point[1] >= lo[1] + span_y * 0.48 and point[2] >= lo[2] + span_z * 0.18
    ]
    if not candidates:
        raise ValueError("head mesh has no scalp candidates under current semantic heuristic")
    rng = random.Random(seed)
    rng.shuffle(candidates)
    guides = []
    for guide_index in range(guide_count):
        vertex_index = candidates[guide_index % len(candidates)]
        root = head.vertices[vertex_index]
        normal = normals[vertex_index]
        root = _add(root, _mul(normal, 0.0006))
        flow = _normalize((
            normal[0] * 0.52 + rng.uniform(-0.22, 0.22),
            normal[1] * 0.38 - 0.42 + rng.uniform(-0.10, 0.10),
            normal[2] * 0.35 - 0.28 + rng.uniform(-0.15, 0.12),
        ))
        step = length / (segments - 1)
        points = [root]
        position = root
        direction = flow
        for segment in range(1, segments):
            t = segment / (segments - 1)
            direction = _normalize((direction[0] * 0.95, direction[1] - 0.10 * t, direction[2] - 0.035 * t))
            position = _add(position, _mul(direction, step))
            points.append(position)
        guides.append(HairGuide(points, normal, root_width, tip_width))
    return HairSystem(guides, seed, "short_cards_v0.2")


def guide_to_ribbon(guide: HairGuide, *, name: str = "hair_card") -> Mesh:
    mesh, _ = guide_to_ribbon_with_uv(guide, name=name)
    return mesh


def guide_to_ribbon_with_uv(guide: HairGuide, *, name: str = "hair_card") -> tuple[Mesh, UVMap]:
    if len(guide.points) < 2:
        raise ValueError("hair guide needs at least two points")
    vertices: list[Vec3] = []
    uvs: list[tuple[float, float]] = []
    previous_side: Vec3 | None = None
    count = len(guide.points)
    for index, point in enumerate(guide.points):
        if index == 0:
            tangent = _sub(guide.points[1], point)
        elif index == count - 1:
            tangent = _sub(point, guide.points[index - 1])
        else:
            tangent = _sub(guide.points[index + 1], guide.points[index - 1])
        tangent = _normalize(tangent)
        side = _cross(tangent, guide.root_normal)
        if sqrt(sum(value * value for value in side)) <= 1e-10:
            side = previous_side or _fallback_side(tangent)
        else:
            side = _normalize(side)
        if previous_side is not None and sum(a * b for a, b in zip(side, previous_side)) < 0.0:
            side = _mul(side, -1.0)
        previous_side = side
        t = index / (count - 1)
        width = guide.root_width * (1.0 - t) + guide.tip_width * t
        half = width * 0.5
        vertices.append(_add(point, _mul(side, -half)))
        vertices.append(_add(point, _mul(side, half)))
        # Hair texture runs root->tip along V; U spans card width.
        uvs.append((0.0, t))
        uvs.append((1.0, t))
    faces = []
    face_uvs = []
    for index in range(count - 1):
        a = index * 2
        b = a + 1
        c = a + 3
        d = a + 2
        face = (a, b, c, d)
        faces.append(face)
        face_uvs.append(face)
    return Mesh(name, vertices, faces), UVMap(uvs, face_uvs, "hair_card_root_to_tip")


def hair_cards(system: HairSystem, *, name: str = "hair_cards") -> Mesh:
    return combine([guide_to_ribbon(guide, name=f"card_{index:04d}") for index, guide in enumerate(system.guides)], name=name)


def hair_cards_with_uv(system: HairSystem, *, name: str = "hair_cards") -> tuple[Mesh, UVMap]:
    vertices: list[Vec3] = []
    faces = []
    uvs: list[tuple[float, float]] = []
    face_uvs = []
    vertex_offset = 0
    uv_offset = 0
    for index, guide in enumerate(system.guides):
        card, card_uv = guide_to_ribbon_with_uv(guide, name=f"card_{index:04d}")
        vertices.extend(card.vertices)
        uvs.extend(card_uv.uvs)
        faces.extend(tuple(vertex + vertex_offset for vertex in face) for face in card.faces)
        face_uvs.extend(tuple(uv + uv_offset for uv in face) for face in card_uv.face_uvs)
        vertex_offset += len(card.vertices)
        uv_offset += len(card_uv.uvs)
    return Mesh(name, vertices, faces), UVMap(uvs, face_uvs, "hair_cards_root_to_tip")


def validate_hair(system: HairSystem) -> dict[str, object]:
    failures = []
    point_counts = []
    for index, guide in enumerate(system.guides):
        point_counts.append(len(guide.points))
        if len(guide.points) < 2:
            failures.append(f"guide {index} has fewer than two points")
        if guide.root_width <= 0.0 or guide.tip_width < 0.0 or guide.tip_width > guide.root_width:
            failures.append(f"guide {index} has invalid taper")
        for point in guide.points:
            if not all(isfinite(value) for value in point):
                failures.append(f"guide {index} contains non-finite point")
    cards, uvmap = hair_cards_with_uv(system) if system.guides else (Mesh("empty", [], []), UVMap([], [], "hair_cards_root_to_tip"))
    return {
        "status": "pass" if not failures else "fail",
        "failures": failures,
        "guides": len(system.guides),
        "point_counts": point_counts,
        "card_vertices": len(cards.vertices),
        "card_faces": len(cards.faces),
        "uvs": len(uvmap.uvs),
        "truth": "Guide/card/UV state only. Groom aesthetics, alpha sorting, scalp coverage and secondary motion have separate gates.",
    }
