#!/usr/bin/env python3
"""Explicit-root short-hair guide generator for AXM hair-card state.

This complements native_hair.generate_short_hair's generic semantic heuristic.
Specialist machines can provide a deterministic canonical root-index set while
reusing the same HairGuide/HairSystem/card pipeline. Root reuse is rejected by
default so density cannot silently come from duplicated anchors.
"""
from __future__ import annotations

import random
from dataclasses import dataclass
from math import sqrt
from typing import Sequence

from native_geometry import Mesh, Vec3, vertex_normals
from native_hair import HairGuide, HairSystem


@dataclass(slots=True)
class ExplicitRootHair:
    system: HairSystem
    root_indices: list[int]


def _add(a: Vec3, b: Vec3) -> Vec3:
    return a[0] + b[0], a[1] + b[1], a[2] + b[2]


def _sub(a: Vec3, b: Vec3) -> Vec3:
    return a[0] - b[0], a[1] - b[1], a[2] - b[2]


def _mul(v: Vec3, scalar: float) -> Vec3:
    return v[0] * scalar, v[1] * scalar, v[2] * scalar


def _dot(a: Vec3, b: Vec3) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _cross(a: Vec3, b: Vec3) -> Vec3:
    return a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]


def _normalize(v: Vec3) -> Vec3:
    length = sqrt(_dot(v, v))
    if length <= 1e-12:
        return 0.0, 1.0, 0.0
    return v[0] / length, v[1] / length, v[2] / length


def _fallback_side(tangent: Vec3) -> Vec3:
    axis = (0.0, 1.0, 0.0) if abs(tangent[1]) < 0.9 else (1.0, 0.0, 0.0)
    return _normalize(_cross(tangent, axis))


def _ensure_outward(direction: Vec3, normal: Vec3, minimum_dot: float = 0.12) -> Vec3:
    normal = _normalize(normal)
    direction = _normalize(direction)
    outward = _dot(direction, normal)
    if outward >= minimum_dot:
        return direction
    tangent = _sub(direction, _mul(normal, outward))
    tangent_length = sqrt(_dot(tangent, tangent))
    tangent = _normalize(tangent) if tangent_length > 1e-12 else _fallback_side(normal)
    return _normalize(_add(_mul(tangent, 0.95), _mul(normal, 0.22)))


def select_root_indices(
    candidate_indices: Sequence[int],
    *,
    guide_count: int,
    seed: int,
    allow_root_reuse: bool = False,
) -> list[int]:
    """Deterministically select canonical roots from an unordered candidate set."""
    if guide_count < 1:
        raise ValueError("guide_count must be positive")
    candidates = sorted({int(index) for index in candidate_indices})
    if not candidates:
        raise ValueError("explicit-root hair requires at least one candidate")
    if guide_count > len(candidates) and not allow_root_reuse:
        raise ValueError(f"requested {guide_count} guides from only {len(candidates)} unique roots")
    rng = random.Random(seed)
    rng.shuffle(candidates)
    return [candidates[index % len(candidates)] for index in range(guide_count)]


def generate_short_hair_from_roots(
    head: Mesh,
    candidate_indices: Sequence[int],
    *,
    guide_count: int,
    segments: int = 5,
    length: float = 0.025,
    root_width: float = 0.0055,
    tip_width: float = 0.0008,
    root_offset: float = 0.0006,
    seed: int = 1,
    allow_root_reuse: bool = False,
    style: str = "short_cards_explicit_roots_v0.1",
) -> ExplicitRootHair:
    if segments < 2:
        raise ValueError("hair needs segments>=2")
    if length <= 0.0 or root_width <= 0.0 or tip_width < 0.0 or tip_width > root_width or root_offset < 0.0:
        raise ValueError("invalid hair dimensions")

    candidates = sorted({int(index) for index in candidate_indices})
    bad = [index for index in candidates if index < 0 or index >= len(head.vertices)]
    if bad:
        raise ValueError(f"explicit hair root indices outside mesh: {bad[:8]}")
    selected = select_root_indices(
        candidates,
        guide_count=guide_count,
        seed=seed,
        allow_root_reuse=allow_root_reuse,
    )

    rng = random.Random(seed)
    # Consume the same candidate shuffle as select_root_indices so later random
    # guide variation remains stable relative to v0.1 selection semantics.
    shuffled = list(candidates)
    rng.shuffle(shuffled)
    normals = vertex_normals(head)
    guides: list[HairGuide] = []

    for vertex_index in selected:
        root = head.vertices[vertex_index]
        normal = _normalize(normals[vertex_index])
        root = _add(root, _mul(normal, root_offset))
        flow = _normalize((
            normal[0] * 0.52 + rng.uniform(-0.20, 0.20),
            normal[1] * 0.42 - 0.30 + rng.uniform(-0.09, 0.09),
            normal[2] * 0.38 - 0.25 + rng.uniform(-0.12, 0.10),
        ))
        flow = _ensure_outward(flow, normal)
        step = length / (segments - 1)
        points = [root]
        position = root
        direction = flow
        for segment in range(1, segments):
            t = segment / (segments - 1)
            direction = _normalize((
                direction[0] * 0.96,
                direction[1] - 0.075 * t,
                direction[2] - 0.035 * t,
            ))
            if segment == 1:
                direction = _ensure_outward(direction, normal)
            position = _add(position, _mul(direction, step))
            points.append(position)
        guides.append(HairGuide(points, normal, root_width, tip_width, group="scalp"))

    return ExplicitRootHair(HairSystem(guides, seed, style), selected)
