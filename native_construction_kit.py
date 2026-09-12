#!/usr/bin/env python3
"""Composable native construction kit for AXM Game Asset Forge.

This module selectively ports reusable geometry mechanisms from the finished
Universal Creation RTS foundry at commit
``a5cc708457b7e8f33e794fdac648ae65d15a0fb4``:

- ``src/axm_uc/surface_geometry.py`` beam/pipe construction;
- ``src/axm_uc/rts_mesh.py`` ring/lathe/rounded-part language;
- ``src/axm_uc/rts_recipes.py`` ladders, barrels, crates, railings and cranes.

The implementation is Game Asset Forge-owned, stdlib-only and Y-up. It does not
import Universal Creation or Blender. These are authored construction helpers,
not structural-engineering, physics, gameplay, aesthetic or CANON claims.
"""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from typing import Any, Iterable, Sequence

from native_geometry import Mesh, Vec3, combine, topology_report, translate
from native_modeling import make_chamfered_box

DONOR = {
    "repo": "mike-axiom-mir/axm-universal-creation",
    "commit": "a5cc708457b7e8f33e794fdac648ae65d15a0fb4",
    "mechanisms": [
        "src/axm_uc/surface_geometry.py",
        "src/axm_uc/rts_mesh.py",
        "src/axm_uc/rts_recipes.py",
    ],
}
SCHEMA = "axm.game-assets.native-construction-kit/v0.1"
EPS = 1e-10


class ConstructionKitError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class SemanticPart:
    part_id: str
    mesh: Mesh
    material_family: str
    semantic_role: str


@dataclass(frozen=True, slots=True)
class ConstructionAssembly:
    name: str
    parts: tuple[SemanticPart, ...]
    receipt: dict[str, Any]

    def combined_mesh(self) -> Mesh:
        return combine((part.mesh for part in self.parts), name=self.name)


def _add(a: Vec3, b: Vec3) -> Vec3:
    return a[0] + b[0], a[1] + b[1], a[2] + b[2]


def _sub(a: Vec3, b: Vec3) -> Vec3:
    return a[0] - b[0], a[1] - b[1], a[2] - b[2]


def _mul(v: Vec3, s: float) -> Vec3:
    return v[0] * s, v[1] * s, v[2] * s


def _cross(a: Vec3, b: Vec3) -> Vec3:
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def _length(v: Vec3) -> float:
    return math.sqrt(sum(component * component for component in v))


def _norm(v: Vec3, label: str = "vector") -> Vec3:
    length = _length(v)
    if length <= EPS:
        raise ConstructionKitError(f"{label} must not be near-zero")
    return tuple(component / length for component in v)  # type: ignore[return-value]


def _finite3(value: Sequence[float], label: str) -> Vec3:
    if len(value) != 3:
        raise ConstructionKitError(f"{label} must contain three coordinates")
    result = tuple(float(item) for item in value)
    if not all(math.isfinite(item) for item in result):
        raise ConstructionKitError(f"{label} must contain finite coordinates")
    return result  # type: ignore[return-value]


def _frame(direction: Vec3) -> tuple[Vec3, Vec3]:
    d = _norm(direction, "construction direction")
    reference = (0.0, 1.0, 0.0) if abs(d[1]) < 0.95 else (0.0, 0.0, 1.0)
    side = _norm(_cross(d, reference), "construction side")
    up = _norm(_cross(side, d), "construction up")
    return side, up


def _safe_positive(value: float, label: str) -> float:
    value = float(value)
    if not math.isfinite(value) or value <= 0.0:
        raise ConstructionKitError(f"{label} must be finite and positive")
    return value


def beam_segment(
    start: Sequence[float],
    end: Sequence[float],
    *,
    width: float,
    depth: float | None = None,
    name: str = "beam",
) -> Mesh:
    """Closed rectangular beam between arbitrary Y-up world points."""
    a = _finite3(start, "start")
    b = _finite3(end, "end")
    width = _safe_positive(width, "width")
    depth = _safe_positive(width if depth is None else depth, "depth")
    direction = _sub(b, a)
    side, up = _frame(direction)
    corners: list[Vec3] = []
    for center in (a, b):
        for s, t in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
            corners.append(_add(center, _add(_mul(side, s * width * 0.5), _mul(up, t * depth * 0.5))))
    faces = [
        (0, 3, 2, 1),
        (4, 5, 6, 7),
        (0, 1, 5, 4),
        (1, 2, 6, 5),
        (2, 3, 7, 6),
        (3, 0, 4, 7),
    ]
    return Mesh(name, corners, faces)


def pipe_path(
    path: Sequence[Sequence[float]],
    *,
    radius: float,
    sides: int = 8,
    name: str = "pipe",
) -> Mesh:
    """Closed polygonal pipe/cable following an authored polyline."""
    radius = _safe_positive(radius, "radius")
    if type(sides) is not int or sides < 3:
        raise ConstructionKitError("pipe sides must be an integer >= 3")
    points = tuple(_finite3(point, f"path[{index}]") for index, point in enumerate(path))
    if len(points) < 2:
        raise ConstructionKitError("pipe path needs at least two points")
    if any(_length(_sub(b, a)) <= EPS for a, b in zip(points, points[1:])):
        raise ConstructionKitError("pipe path contains a zero-length segment")

    rings: list[list[Vec3]] = []
    for index, center in enumerate(points):
        before = points[max(0, index - 1)]
        after = points[min(len(points) - 1, index + 1)]
        side, up = _frame(_sub(after, before))
        ring = []
        for j in range(sides):
            angle = math.tau * j / sides
            offset = _add(_mul(side, radius * math.cos(angle)), _mul(up, radius * math.sin(angle)))
            ring.append(_add(center, offset))
        rings.append(ring)

    vertices = [vertex for ring in rings for vertex in ring]
    faces: list[tuple[int, ...]] = []
    for ring_index in range(len(rings) - 1):
        base = ring_index * sides
        nxt = (ring_index + 1) * sides
        for j in range(sides):
            k = (j + 1) % sides
            faces.append((base + j, base + k, nxt + k, nxt + j))
    faces.append(tuple(reversed(range(sides))))
    last = (len(rings) - 1) * sides
    faces.append(tuple(last + j for j in range(sides)))
    return Mesh(name, vertices, faces)


def torus_ring(
    center: Sequence[float],
    *,
    radius: float,
    tube: float,
    axis: str = "y",
    ratio: float = 1.0,
    major_segments: int = 20,
    minor_segments: int = 6,
    name: str = "ring",
) -> Mesh:
    """Closed torus-like ring, optionally elliptical in one radial axis."""
    c = _finite3(center, "center")
    radius = _safe_positive(radius, "radius")
    tube = _safe_positive(tube, "tube")
    if axis not in {"x", "y", "z"}:
        raise ConstructionKitError("ring axis must be x, y or z")
    if type(major_segments) is not int or major_segments < 3 or type(minor_segments) is not int or minor_segments < 3:
        raise ConstructionKitError("ring segment counts must be integers >= 3")
    if not math.isfinite(ratio) or ratio <= 0.0:
        raise ConstructionKitError("ring ratio must be finite and positive")

    def orient(v: Vec3) -> Vec3:
        if axis == "y":
            return v
        if axis == "x":
            return v[1], v[2], v[0]
        return v[0], -v[2], v[1]

    vertices: list[Vec3] = []
    for i in range(major_segments):
        theta = math.tau * i / major_segments
        for j in range(minor_segments):
            phi = math.tau * j / minor_segments
            rr = radius + tube * math.cos(phi)
            local = (rr * math.cos(theta), tube * math.sin(phi), rr * math.sin(theta) * ratio)
            vertices.append(_add(c, orient(local)))
    faces = []
    for i in range(major_segments):
        ni = (i + 1) % major_segments
        for j in range(minor_segments):
            nj = (j + 1) % minor_segments
            faces.append((
                i * minor_segments + j,
                ni * minor_segments + j,
                ni * minor_segments + nj,
                i * minor_segments + nj,
            ))
    return Mesh(name, vertices, faces)


def lathe_profile(
    profile: Sequence[Sequence[float]],
    *,
    center: Sequence[float] = (0.0, 0.0, 0.0),
    axis: str = "y",
    segments: int = 18,
    name: str = "lathe",
) -> Mesh:
    """Revolve a radius/height profile into a closed authored solid."""
    if len(profile) < 2:
        raise ConstructionKitError("lathe profile needs at least two points")
    if axis not in {"x", "y", "z"}:
        raise ConstructionKitError("lathe axis must be x, y or z")
    if type(segments) is not int or segments < 3:
        raise ConstructionKitError("lathe segments must be an integer >= 3")
    c = _finite3(center, "center")
    points: list[tuple[float, float]] = []
    for index, row in enumerate(profile):
        if len(row) != 2:
            raise ConstructionKitError(f"profile[{index}] must contain radius,height")
        radius, height = float(row[0]), float(row[1])
        if not math.isfinite(radius) or radius < 0.0 or not math.isfinite(height):
            raise ConstructionKitError(f"profile[{index}] is invalid")
        if index and radius <= EPS and points[-1][0] <= EPS:
            raise ConstructionKitError("lathe profile has consecutive zero-radius points")
        points.append((radius, height))

    def orient(local: Vec3) -> Vec3:
        if axis == "y":
            return local
        if axis == "x":
            return local[1], local[2], local[0]
        return local[0], -local[2], local[1]

    vertices: list[Vec3] = []
    levels: list[list[int]] = []
    for radius, height in points:
        if radius <= EPS:
            levels.append([len(vertices)])
            vertices.append(_add(c, orient((0.0, height, 0.0))))
        else:
            level = []
            for i in range(segments):
                angle = math.tau * i / segments
                level.append(len(vertices))
                vertices.append(_add(c, orient((radius * math.cos(angle), height, radius * math.sin(angle)))))
            levels.append(level)

    faces: list[tuple[int, ...]] = []
    for left, right in zip(levels, levels[1:]):
        if len(left) == 1 and len(right) > 1:
            apex = left[0]
            for i in range(segments):
                j = (i + 1) % segments
                faces.append((apex, right[j], right[i]))
        elif len(left) > 1 and len(right) == 1:
            apex = right[0]
            for i in range(segments):
                j = (i + 1) % segments
                faces.append((left[i], left[j], apex))
        else:
            for i in range(segments):
                j = (i + 1) % segments
                faces.append((left[i], left[j], right[j], right[i]))

    # If the caller supplied a non-zero end radius, close it explicitly.
    if len(levels[0]) > 1:
        radius, height = points[0]
        center_index = len(vertices)
        vertices.append(_add(c, orient((0.0, height, 0.0))))
        for i in range(segments):
            j = (i + 1) % segments
            faces.append((center_index, levels[0][i], levels[0][j]))
    if len(levels[-1]) > 1:
        radius, height = points[-1]
        center_index = len(vertices)
        vertices.append(_add(c, orient((0.0, height, 0.0))))
        for i in range(segments):
            j = (i + 1) % segments
            faces.append((center_index, levels[-1][j], levels[-1][i]))
    return Mesh(name, vertices, faces)


def rounded_box(
    center: Sequence[float],
    size: Sequence[float],
    *,
    chamfer: float,
    name: str = "rounded-box",
) -> Mesh:
    c = _finite3(center, "center")
    if len(size) != 3:
        raise ConstructionKitError("size must contain width,height,depth")
    width, height, depth = (_safe_positive(value, f"size[{index}]") for index, value in enumerate(size))
    if not math.isfinite(chamfer) or chamfer < 0.0 or chamfer >= min(width, height) * 0.5:
        raise ConstructionKitError("chamfer must be finite, non-negative and below half the smaller XY dimension")
    return translate(make_chamfered_box(width, height, depth, chamfer, name=name), c, name=name)


def _part(part_id: str, mesh: Mesh, material_family: str, semantic_role: str) -> SemanticPart:
    report = topology_report(mesh)
    if report["invalid_indices"] or report["degenerate_faces"] or not report["closed_two_manifold_candidate"]:
        raise ConstructionKitError(f"part {part_id!r} is not a closed valid shell: {report}")
    return SemanticPart(part_id, mesh, material_family, semantic_role)


def _assembly(name: str, parts: Iterable[SemanticPart], recipe: str) -> ConstructionAssembly:
    ordered = tuple(parts)
    if not ordered:
        raise ConstructionKitError("construction assembly needs at least one part")
    ids = [part.part_id for part in ordered]
    if len(ids) != len(set(ids)):
        raise ConstructionKitError("construction assembly part ids must be unique")
    receipt: dict[str, Any] = {
        "schema": SCHEMA,
        "name": name,
        "recipe": recipe,
        "coordinate_system": "Y-up",
        "part_count": len(ordered),
        "parts": [
            {
                "part_id": part.part_id,
                "mesh": part.mesh.name,
                "material_family": part.material_family,
                "semantic_role": part.semantic_role,
                "topology": topology_report(part.mesh),
            }
            for part in ordered
        ],
        "provenance": {"donor": DONOR, "implementation": "AXM Game Asset Forge native adaptation"},
        "truth_boundary": {
            "authored_geometry": True,
            "physics_simulation": False,
            "structural_engineering_proven": False,
            "collision_suitability_proven": False,
            "aesthetic_quality_proven": False,
            "automatic_genome_mutation": False,
            "automatic_canon": False,
        },
    }
    receipt["receipt_digest"] = "sha256:" + hashlib.sha256(
        json.dumps(receipt, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    return ConstructionAssembly(name, ordered, receipt)


def build_ladder(
    *,
    name: str = "ladder",
    center_x: float = 0.0,
    base_y: float = 0.0,
    z: float = 0.0,
    height: float = 2.4,
    width: float = 0.46,
    rung_spacing: float = 0.32,
) -> ConstructionAssembly:
    height = _safe_positive(height, "height")
    width = _safe_positive(width, "width")
    rung_spacing = _safe_positive(rung_spacing, "rung_spacing")
    parts: list[SemanticPart] = []
    for side in (-1.0, 1.0):
        x = center_x + side * width * 0.5
        mesh = beam_segment((x, base_y, z), (x, base_y + height, z), width=0.06, depth=0.06, name=f"{name}-rail")
        parts.append(_part(f"rail-{int(side)}", mesh, "wood", "ladder-rail"))
    count = max(2, int(height / rung_spacing))
    for index in range(count):
        y = base_y + min(height - 0.12, 0.20 + index * rung_spacing)
        mesh = beam_segment(
            (center_x - width * 0.5, y, z),
            (center_x + width * 0.5, y, z),
            width=0.045,
            depth=0.055,
            name=f"{name}-rung",
        )
        parts.append(_part(f"rung-{index:02d}", mesh, "steel", "ladder-rung"))
    return _assembly(name, parts, "ladder")


def build_barrel(
    *,
    name: str = "barrel",
    center: Sequence[float] = (0.0, 0.0, 0.0),
    radius: float = 0.32,
    height: float = 0.85,
) -> ConstructionAssembly:
    c = _finite3(center, "center")
    radius = _safe_positive(radius, "radius")
    height = _safe_positive(height, "height")
    body = lathe_profile(
        ((0.0, 0.0), (radius * 0.92, 0.0), (radius, height * 0.08), (radius, height * 0.92), (radius * 0.92, height), (0.0, height)),
        center=c,
        name=f"{name}-body",
    )
    parts = [_part("body", body, "salvage_metal", "barrel-shell")]
    for index, factor in enumerate((0.10, 0.32, 0.74, 0.94)):
        ring = torus_ring(
            (c[0], c[1] + height * factor, c[2]),
            radius=radius,
            tube=max(0.012, radius * 0.07),
            name=f"{name}-hoop",
        )
        parts.append(_part(f"hoop-{index}", ring, "steel", "barrel-reinforcement"))
    return _assembly(name, parts, "barrel")


def build_crate(
    *,
    name: str = "crate",
    center: Sequence[float] = (0.0, 0.0, 0.0),
    size: Sequence[float] = (0.9, 0.65, 0.62),
) -> ConstructionAssembly:
    c = _finite3(center, "center")
    if len(size) != 3:
        raise ConstructionKitError("crate size must contain width,height,depth")
    w, h, d = (_safe_positive(value, f"size[{index}]") for index, value in enumerate(size))
    parts: list[SemanticPart] = []
    body = rounded_box(c, (w, h, d), chamfer=min(w, h) * 0.04, name=f"{name}-body")
    parts.append(_part("body", body, "wood", "crate-body"))
    for index, x in enumerate((-w * 0.41, w * 0.41)):
        strap = rounded_box((c[0] + x, c[1], c[2]), (w * 0.08, h * 1.05, d * 1.04), chamfer=min(w * 0.08, h * 1.05) * 0.12, name=f"{name}-strap")
        parts.append(_part(f"strap-{index}", strap, "steel", "crate-strap"))
    latch = rounded_box((c[0], c[1] + h * 0.18, c[2] + d * 0.52), (w * 0.16, h * 0.18, d * 0.06), chamfer=min(w * 0.16, h * 0.18) * 0.12, name=f"{name}-latch")
    parts.append(_part("latch", latch, "steel", "crate-latch"))
    return _assembly(name, parts, "crate")


def build_railing(
    start: Sequence[float],
    end: Sequence[float],
    *,
    name: str = "railing",
    height: float = 0.9,
    post_spacing: float = 0.9,
) -> ConstructionAssembly:
    a = _finite3(start, "start")
    b = _finite3(end, "end")
    height = _safe_positive(height, "height")
    post_spacing = _safe_positive(post_spacing, "post_spacing")
    span = _length(_sub(b, a))
    if span <= EPS:
        raise ConstructionKitError("railing span must be non-zero")
    count = max(2, math.ceil(span / post_spacing) + 1)
    parts: list[SemanticPart] = []
    top_a = (a[0], a[1] + height, a[2])
    top_b = (b[0], b[1] + height, b[2])
    parts.append(_part("top-rail", pipe_path((top_a, top_b), radius=0.035, sides=8, name=f"{name}-top"), "steel", "guardrail"))
    for index in range(count):
        t = index / (count - 1)
        base = tuple(a[i] + (b[i] - a[i]) * t for i in range(3))
        top = (base[0], base[1] + height, base[2])
        parts.append(_part(f"post-{index:02d}", pipe_path((base, top), radius=0.03, sides=8, name=f"{name}-post"), "steel", "railing-post"))
    return _assembly(name, parts, "railing")


def build_crane(
    *,
    name: str = "crane",
    center: Sequence[float] = (0.0, 0.0, 0.0),
    height: float = 4.0,
    boom_length: float = 3.0,
) -> ConstructionAssembly:
    c = _finite3(center, "center")
    height = _safe_positive(height, "height")
    if not math.isfinite(boom_length) or abs(boom_length) <= EPS:
        raise ConstructionKitError("boom_length must be finite and non-zero")
    parts: list[SemanticPart] = []
    for index, dx in enumerate((-0.32, 0.32)):
        mesh = beam_segment((c[0] + dx, c[1] + 0.2, c[2]), (c[0] + dx, c[1] + height, c[2]), width=0.17, depth=0.17, name=f"{name}-mast")
        parts.append(_part(f"mast-{index}", mesh, "salvage_metal", "crane-mast"))
    start = (c[0], c[1] + height, c[2])
    end = (c[0] + boom_length, c[1] + height + boom_length * 0.4, c[2])
    for index, dz in enumerate((-0.18, 0.18)):
        mesh = beam_segment(_add(start, (0.0, 0.0, dz)), _add(end, (0.0, 0.0, dz)), width=0.17, depth=0.17, name=f"{name}-boom")
        parts.append(_part(f"boom-{index}", mesh, "salvage_metal", "crane-boom"))
    for index in range(6):
        t = index / 6.0
        u = (index + 1) / 6.0
        a = _add(start, (boom_length * t, boom_length * 0.4 * t, -0.18))
        b = _add(start, (boom_length * u, boom_length * 0.4 * u, 0.18))
        parts.append(_part(f"brace-{index}", beam_segment(a, b, width=0.06, depth=0.06, name=f"{name}-brace"), "steel", "boom-crossbrace"))
    cable_end = (end[0], c[1] + 1.5, c[2])
    parts.append(_part("load-cable", pipe_path((end, cable_end), radius=0.027, sides=6, name=f"{name}-cable"), "steel", "load-cable"))
    hook_path = (cable_end, (end[0] - 0.1, c[1] + 1.3, c[2]), (end[0] + 0.1, c[1] + 1.2, c[2]), (end[0] + 0.18, c[1] + 1.36, c[2]))
    parts.append(_part("hook", pipe_path(hook_path, radius=0.07, sides=7, name=f"{name}-hook"), "steel", "crane-hook"))
    hydraulic = ((c[0], c[1] + height * 0.5, c[2]), (c[0] + boom_length * 0.5, c[1] + height + boom_length * 0.2, c[2]))
    parts.append(_part("hydraulic", pipe_path(hydraulic, radius=0.095, sides=8, name=f"{name}-hydraulic"), "steel", "hydraulic-strut"))
    return _assembly(name, parts, "crane")
