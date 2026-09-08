#!/usr/bin/env python3
"""Source-grounded rigid Sentinel armor over the pinned hm08 human body.

This organ establishes a first real armored character silhouette without
mutating the canonical human or undersuit. Torso/shoulder/forearm/shin pieces
are separate semantic meshes. Placement is derived from the current body
surface and bounded physical clearances; this is a silhouette/manufacturing
pass, not yet production armor fit, articulation, or deformation proof.
"""
from __future__ import annotations

import json
from math import sqrt
from pathlib import Path

from native_geometry import Mesh, bounds, combine, scale, topology_report
from native_hardsurface import sentinel_armor_plate
from native_modeling import make_chamfered_box
from native_pbr import PaintedMetalSpec, write_painted_metal
from native_uv import UVMap, box_project_world, validate_uv

SCHEMA = "axm.game-assets.hm08-sentinel-armor.v0.1"


def _sub(a, b):
    return a[0] - b[0], a[1] - b[1], a[2] - b[2]


def _add(a, b):
    return a[0] + b[0], a[1] + b[1], a[2] + b[2]


def _mul(v, s: float):
    return v[0] * s, v[1] * s, v[2] * s


def _dot(a, b) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _cross(a, b):
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def _length(v) -> float:
    return sqrt(_dot(v, v))


def _normalize(v):
    length = _length(v)
    if length <= 1e-12:
        raise ValueError("cannot normalize zero armor axis")
    return v[0] / length, v[1] / length, v[2] / length


def _centroid(points):
    if not points:
        raise ValueError("armor anchor selection is empty")
    inv = 1.0 / len(points)
    return (
        sum(p[0] for p in points) * inv,
        sum(p[1] for p in points) * inv,
        sum(p[2] for p in points) * inv,
    )


def _transform_local(mesh: Mesh, center, axis_y=(0.0, 1.0, 0.0), forward_hint=(0.0, 0.0, 1.0), *, name: str) -> Mesh:
    """Place local X/Y/Z geometry on an orthonormal body-derived frame."""
    by = _normalize(axis_y)
    hint = _normalize(forward_hint)
    bz_raw = _sub(hint, _mul(by, _dot(hint, by)))
    if _length(bz_raw) <= 1e-8:
        fallback = (0.0, 1.0, 0.0) if abs(by[1]) < 0.9 else (1.0, 0.0, 0.0)
        bz_raw = _sub(fallback, _mul(by, _dot(fallback, by)))
    bz = _normalize(bz_raw)
    bx = _normalize(_cross(by, bz))
    vertices = []
    for x, y, z in mesh.vertices:
        world = _add(center, _add(_mul(bx, x), _add(_mul(by, y), _mul(bz, z))))
        vertices.append(world)
    return Mesh(name, vertices, list(mesh.faces))


def _region(body: Mesh, predicate):
    return [point for point in body.vertices if predicate(point)]


def _scaled_plate(width: float, height: float, depth: float, *, level: int, name: str) -> Mesh:
    plate, _ = sentinel_armor_plate(level)
    lo, hi = bounds(plate)
    span = (hi[0] - lo[0], hi[1] - lo[1], hi[2] - lo[2])
    scaled = scale(plate, (width / span[0], height / span[1], depth / span[2]), name=name)
    return scaled


def _arm_axis(body: Mesh, sign: float):
    candidates = _region(
        body,
        lambda p: p[0] * sign > 0.265 and -0.04 <= p[1] <= 0.46,
    )
    if len(candidates) < 20:
        raise ValueError("not enough canonical arm vertices for armor anchors")
    abs_x = sorted(abs(p[0]) for p in candidates)
    inner_cut = abs_x[max(0, int(len(abs_x) * 0.18) - 1)]
    outer_cut = abs_x[min(len(abs_x) - 1, int(len(abs_x) * 0.72))]
    inner = [p for p in candidates if abs(p[0]) <= inner_cut + 1e-9]
    outer = [p for p in candidates if abs(p[0]) >= outer_cut - 1e-9]
    elbowish = _centroid(inner)
    wristish = _centroid(outer)
    axis = _sub(wristish, elbowish)
    return elbowish, wristish, axis


def _shin_axis(body: Mesh, sign: float):
    candidates = _region(
        body,
        lambda p: p[0] * sign > 0.015 and abs(p[0]) < 0.20 and -0.72 <= p[1] <= -0.28,
    )
    if len(candidates) < 20:
        raise ValueError("not enough canonical shin vertices for armor anchors")
    top = [p for p in candidates if -0.43 <= p[1] <= -0.30]
    bottom = [p for p in candidates if -0.68 <= p[1] <= -0.55]
    top_center = _centroid(top)
    bottom_center = _centroid(bottom)
    axis = _sub(bottom_center, top_center)
    return top_center, bottom_center, axis


def build_sentinel_armor(body_m: Mesh) -> tuple[dict[str, Mesh], dict[str, UVMap], dict[str, object]]:
    body_lo, body_hi = bounds(body_m)

    chest_points = _region(body_m, lambda p: abs(p[0]) <= 0.235 and 0.18 <= p[1] <= 0.50)
    if len(chest_points) < 40:
        raise ValueError("canonical torso anchor region is unexpectedly sparse")
    chest_lo = tuple(min(p[i] for p in chest_points) for i in range(3))
    chest_hi = tuple(max(p[i] for p in chest_points) for i in range(3))
    chest_width = min(0.42, max(0.34, (chest_hi[0] - chest_lo[0]) * 0.96))
    chest_height = 0.285
    chest_depth = 0.040
    chest_y = 0.345
    front_clearance = 0.010
    back_clearance = 0.009

    front_plate = _scaled_plate(chest_width, chest_height, chest_depth, level=3, name="sentinel_front_core")
    front_center = (0.0, chest_y, chest_hi[2] + front_clearance + chest_depth * 0.5)
    front_plate = _transform_local(front_plate, front_center, forward_hint=(0.0, 0.0, 1.0), name="sentinel_front_core")

    back_plate = _scaled_plate(chest_width * 0.91, chest_height * 0.94, chest_depth * 0.88, level=2, name="sentinel_back_core")
    back_center = (0.0, chest_y - 0.005, chest_lo[2] - back_clearance - chest_depth * 0.44)
    back_plate = _transform_local(back_plate, back_center, forward_hint=(0.0, 0.0, -1.0), name="sentinel_back_core")

    abdomen_parts = []
    for y, width in ((0.145, 0.285), (0.065, 0.255), (-0.015, 0.225)):
        band = _region(body_m, lambda p, yy=y: abs(p[0]) <= 0.18 and yy - 0.035 <= p[1] <= yy + 0.035)
        if not band:
            continue
        front_z = max(p[2] for p in band)
        piece = make_chamfered_box(width, 0.052, 0.026, 0.014, name="abdomen_plate")
        abdomen_parts.append(_transform_local(piece, (0.0, y, front_z + 0.018), name=f"abdomen_plate_{len(abdomen_parts)}"))
    torso = combine([front_plate, back_plate, *abdomen_parts], name="sentinel_armor_torso")

    shoulder_parts = []
    shoulder_centers = {}
    for side, sign in (("left", -1.0), ("right", 1.0)):
        region = _region(body_m, lambda p, s=sign: p[0] * s > 0.18 and p[0] * s < 0.34 and 0.30 <= p[1] <= 0.52)
        center = _centroid(region)
        shoulder_centers[side] = center
        piece = make_chamfered_box(0.165, 0.105, 0.115, 0.026, name=f"{side}_shoulder")
        placed = _transform_local(
            piece,
            (center[0] + sign * 0.018, center[1] + 0.015, center[2] + 0.010),
            name=f"sentinel_{side}_shoulder",
        )
        shoulder_parts.append(placed)
    shoulders = combine(shoulder_parts, name="sentinel_armor_shoulders")

    forearm_parts = []
    forearm_receipts = {}
    for side, sign in (("left", -1.0), ("right", 1.0)):
        inner, outer, axis = _arm_axis(body_m, sign)
        axis_len = _length(axis)
        center = _add(inner, _mul(axis, 0.58))
        length = max(0.15, min(0.24, axis_len * 0.54))
        piece = make_chamfered_box(0.090, length, 0.075, 0.018, name=f"{side}_forearm")
        placed = _transform_local(piece, _add(center, (0.0, 0.0, 0.014)), axis_y=axis, name=f"sentinel_{side}_forearm")
        forearm_parts.append(placed)
        forearm_receipts[side] = {"inner": list(inner), "outer": list(outer), "axis_length_m": axis_len, "armor_length_m": length}
    forearms = combine(forearm_parts, name="sentinel_armor_forearms")

    shin_parts = []
    shin_receipts = {}
    for side, sign in (("left", -1.0), ("right", 1.0)):
        top, bottom, axis = _shin_axis(body_m, sign)
        axis_len = _length(axis)
        center = _add(top, _mul(axis, 0.56))
        length = max(0.23, min(0.31, axis_len * 0.82))
        piece = make_chamfered_box(0.105, length, 0.070, 0.020, name=f"{side}_shin")
        placed = _transform_local(piece, _add(center, (0.0, 0.0, 0.020)), axis_y=axis, name=f"sentinel_{side}_shin")
        shin_parts.append(placed)
        shin_receipts[side] = {"top": list(top), "bottom": list(bottom), "axis_length_m": axis_len, "armor_length_m": length}
    shins = combine(shin_parts, name="sentinel_armor_shins")

    groups = {"torso": torso, "shoulders": shoulders, "forearms": forearms, "shins": shins}
    uv = {name: box_project_world(mesh, world_units_per_tile=0.12) for name, mesh in groups.items()}
    topology = {name: topology_report(mesh) for name, mesh in groups.items()}
    uv_reports = {name: validate_uv(groups[name], uv[name]) for name in groups}
    for name in groups:
        if not topology[name]["closed_two_manifold_candidate"]:
            raise ValueError(f"armor group {name} contains open/non-manifold geometry: {topology[name]}")
        if uv_reports[name]["status"] != "pass":
            raise ValueError(f"armor group {name} UV invalid: {uv_reports[name]}")

    evidence: dict[str, object] = {
        "schema": SCHEMA,
        "group_order": ["torso", "shoulders", "forearms", "shins"],
        "group_topology": topology,
        "group_uv": uv_reports,
        "body_bounds_m": {"min": list(body_lo), "max": list(body_hi)},
        "torso_anchor": {
            "source_bounds_min": list(chest_lo),
            "source_bounds_max": list(chest_hi),
            "front_center": list(front_center),
            "back_center": list(back_center),
            "front_clearance_m": front_clearance,
            "back_clearance_m": back_clearance,
            "abdomen_plate_count": len(abdomen_parts),
        },
        "shoulder_centers": {key: list(value) for key, value in shoulder_centers.items()},
        "forearm_anchors": forearm_receipts,
        "shin_anchors": shin_receipts,
        "truth": {
            "canonical_body_mutated": False,
            "rigid_layer": True,
            "production_fit_claim": False,
            "deformation_clearance_claim": False,
            "notes": [
                "Armor anchors are derived from the current canonical human body in meters; rigid meshes remain separate semantic state above the fitted undersuit.",
                "The torso reuses the Forge's level-3 manufactured plate language so this is not a blank primitive-only silhouette.",
                "Limb pieces are aligned to body-derived arm/shin axes. Motion clearance and joint segmentation still require pose/deformation evidence.",
                "This first armor pass targets whole-character silhouette and material separation, not final hero-closeup manufacturing detail."
            ],
        },
    }
    return groups, uv, evidence


def write_sentinel_armor_materials(output: str | Path, *, size: int = 256, seed: int = 101021) -> dict[str, object]:
    root = Path(output)
    primary = write_painted_metal(
        root / "primary",
        size=size,
        seed=seed,
        spec=PaintedMetalSpec(
            paint_rgb=(45, 56, 55), metal_rgb=(112, 119, 121),
            paint_roughness=0.43, metal_roughness=0.25, wear=0.18,
            scratches=10, grain_scale=36.0,
            height_grain_amplitude=0.035, height_broad_amplitude=0.018,
            height_scratch_depth=0.075, height_pit_depth=0.045,
            base_grain_variation=0.075, roughness_grain_variation=0.045,
            normal_strength=2.2,
        ),
    )
    secondary = write_painted_metal(
        root / "secondary",
        size=size,
        seed=seed + 37,
        spec=PaintedMetalSpec(
            paint_rgb=(24, 30, 34), metal_rgb=(91, 100, 105),
            paint_roughness=0.50, metal_roughness=0.30, wear=0.12,
            scratches=7, grain_scale=40.0,
            height_grain_amplitude=0.028, height_broad_amplitude=0.012,
            height_scratch_depth=0.055, height_pit_depth=0.032,
            base_grain_variation=0.060, roughness_grain_variation=0.040,
            normal_strength=1.8,
        ),
    )
    return {"schema": "axm.game-assets.sentinel-armor-materials.v0.1", "primary": primary, "secondary": secondary}


if __name__ == "__main__":
    from native_hm08_undersuit import _load_identity_body
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("output", nargs="?", default="build/hm08-armor")
    parser.add_argument("--texture-size", type=int, default=128)
    args = parser.parse_args()
    body, _uv, _state = _load_identity_body()
    groups, uvs, evidence = build_sentinel_armor(body)
    materials = write_sentinel_armor_materials(Path(args.output) / "materials", size=args.texture_size)
    Path(args.output).mkdir(parents=True, exist_ok=True)
    packet = {"evidence": evidence, "materials": materials, "groups": {name: {"vertices": len(mesh.vertices), "faces": len(mesh.faces), "uvs": len(uvs[name].uvs)} for name, mesh in groups.items()}}
    (Path(args.output) / "armor.json").write_text(json.dumps(packet, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(packet, indent=2))
