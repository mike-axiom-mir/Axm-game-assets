#!/usr/bin/env python3
"""Body-grounded deterministic rigid armor substrate for Sentinel-01.

This organ reuses the Forge hard-surface/PBR kernels but anchors the result to
the current complete hm08 human body. It is a first readable armor silhouette,
not a production armor/tailoring claim. Every component remains a separate
closed constructive shell before material grouping.
"""
from __future__ import annotations

import json
from math import cos, radians, sin
from pathlib import Path

from native_geometry import Mesh, bounds, combine, scale, topology_report, translate
from native_hardsurface import sentinel_armor_plate
from native_modeling import make_chamfered_box
from native_pbr import PaintedMetalSpec, write_painted_metal
from native_uv import UVMap, box_project_world, validate_uv

SCHEMA = "axm.game-assets.hm08-sentinel-rigid-armor.v0.1"


def _rotate_y(mesh: Mesh, degrees: float, *, name: str | None = None) -> Mesh:
    angle = radians(degrees)
    c, s = cos(angle), sin(angle)
    return Mesh(
        name or mesh.name,
        [(x * c + z * s, y, -x * s + z * c) for x, y, z in mesh.vertices],
        list(mesh.faces),
    )


def _rotate_z(mesh: Mesh, degrees: float, *, name: str | None = None) -> Mesh:
    angle = radians(degrees)
    c, s = cos(angle), sin(angle)
    return Mesh(
        name or mesh.name,
        [(x * c - y * s, x * s + y * c, z) for x, y, z in mesh.vertices],
        list(mesh.faces),
    )


def _place(mesh: Mesh, *, x: float = 0.0, y: float = 0.0, z: float = 0.0, rz: float = 0.0, ry: float = 0.0, name: str | None = None) -> Mesh:
    out = mesh
    if abs(ry) > 1e-12:
        out = _rotate_y(out, ry)
    if abs(rz) > 1e-12:
        out = _rotate_z(out, rz)
    return translate(out, (x, y, z), name=name)


def _region_depth(body: Mesh, *, y_center: float, y_half: float, x_limit: float) -> tuple[float, float]:
    points = [
        point for point in body.vertices
        if abs(point[1] - y_center) <= y_half and abs(point[0]) <= x_limit
    ]
    if not points:
        points = list(body.vertices)
    zs = [point[2] for point in points]
    return min(zs), max(zs)


def _closed_report(mesh: Mesh) -> dict[str, object]:
    report = topology_report(mesh)
    if report["invalid_indices"] or report["degenerate_faces"] or report["nonmanifold_edges"]:
        raise ValueError(f"armor group topology invalid: {report}")
    return report


def build_sentinel_rigid_armor(body_m: Mesh) -> tuple[Mesh, UVMap, Mesh, UVMap, dict[str, object]]:
    lo, hi = bounds(body_m)
    height = hi[1] - lo[1]
    half_width = max(abs(lo[0]), abs(hi[0]), 1e-6)
    if not (1.4 <= height <= 2.2):
        raise ValueError(f"Sentinel armor expects a human-scale body, got height={height}")

    def yf(fraction: float) -> float:
        return lo[1] + height * fraction

    chest_y = yf(0.685)
    shoulder_y = yf(0.785)
    forearm_y = yf(0.615)
    hip_y = yf(0.465)
    thigh_y = yf(0.350)
    knee_y = yf(0.245)
    shin_y = yf(0.130)
    chest_back_z, chest_front_z = _region_depth(
        body_m,
        y_center=chest_y,
        y_half=height * 0.105,
        x_limit=half_width * 0.48,
    )

    primary_parts: list[Mesh] = []
    accent_parts: list[Mesh] = []
    primary_names: list[str] = []
    accent_names: list[str] = []

    chest_source, chest_detail = sentinel_armor_plate(3)
    chest = scale(chest_source, (0.72, 0.52, 0.74), name="sentinel_chest_core")
    primary_parts.append(_place(chest, y=chest_y, z=chest_front_z + 0.033, name="chest_core"))
    primary_names.append("chest_core")

    back = scale(chest_source, (0.68, 0.49, 0.68), name="sentinel_back_core")
    primary_parts.append(_place(back, y=chest_y, z=chest_back_z - 0.031, ry=180.0, name="back_core"))
    primary_names.append("back_core")

    shoulder_x = half_width * 0.50
    pauldron = make_chamfered_box(0.175, 0.145, 0.072, 0.026, name="pauldron")
    for side, sign in (("left", -1.0), ("right", 1.0)):
        rz = 18.0 * sign
        primary_parts.append(_place(pauldron, x=sign * shoulder_x, y=shoulder_y, z=0.035, rz=rz, name=f"{side}_pauldron"))
        primary_names.append(f"{side}_pauldron")

    forearm_x = half_width * 0.70
    forearm = make_chamfered_box(0.095, 0.235, 0.060, 0.018, name="forearm_guard")
    for side, sign in (("left", -1.0), ("right", 1.0)):
        rz = 31.0 * sign
        primary_parts.append(_place(forearm, x=sign * forearm_x, y=forearm_y, z=0.045, rz=rz, name=f"{side}_forearm_guard"))
        primary_names.append(f"{side}_forearm_guard")

    hip_x = half_width * 0.31
    hip_plate = make_chamfered_box(0.105, 0.175, 0.052, 0.018, name="hip_plate")
    for side, sign in (("left", -1.0), ("right", 1.0)):
        primary_parts.append(_place(hip_plate, x=sign * hip_x, y=hip_y, z=0.055, rz=8.0 * sign, name=f"{side}_hip_plate"))
        primary_names.append(f"{side}_hip_plate")

    thigh_x = half_width * 0.235
    thigh_plate = make_chamfered_box(0.145, 0.300, 0.050, 0.022, name="thigh_plate")
    knee_plate = make_chamfered_box(0.135, 0.115, 0.066, 0.025, name="knee_plate")
    shin_plate = make_chamfered_box(0.118, 0.315, 0.048, 0.020, name="shin_plate")
    for side, sign in (("left", -1.0), ("right", 1.0)):
        primary_parts.append(_place(thigh_plate, x=sign * thigh_x, y=thigh_y, z=0.095, rz=2.5 * sign, name=f"{side}_thigh_plate"))
        primary_parts.append(_place(knee_plate, x=sign * thigh_x, y=knee_y, z=0.115, name=f"{side}_knee_plate"))
        primary_parts.append(_place(shin_plate, x=sign * thigh_x * 0.92, y=shin_y, z=0.078, rz=1.5 * sign, name=f"{side}_shin_plate"))
        primary_names.extend([f"{side}_thigh_plate", f"{side}_knee_plate", f"{side}_shin_plate"])

    chest_spine = make_chamfered_box(0.060, 0.255, 0.026, 0.010, name="chest_spine")
    accent_parts.append(_place(chest_spine, y=chest_y, z=chest_front_z + 0.085, name="chest_spine"))
    accent_names.append("chest_spine")

    chest_rail = make_chamfered_box(0.032, 0.245, 0.022, 0.007, name="chest_rail")
    for side, sign in (("left", -1.0), ("right", 1.0)):
        accent_parts.append(_place(chest_rail, x=sign * 0.145, y=chest_y - 0.008, z=chest_front_z + 0.082, name=f"{side}_chest_rail"))
        accent_names.append(f"{side}_chest_rail")

    back_spine = make_chamfered_box(0.052, 0.325, 0.024, 0.009, name="back_spine")
    accent_parts.append(_place(back_spine, y=chest_y - 0.010, z=chest_back_z - 0.071, ry=180.0, name="back_spine"))
    accent_names.append("back_spine")

    limb_rail = make_chamfered_box(0.026, 0.175, 0.018, 0.006, name="limb_rail")
    for side, sign in (("left", -1.0), ("right", 1.0)):
        accent_parts.append(_place(limb_rail, x=sign * forearm_x, y=forearm_y, z=0.080, rz=31.0 * sign, name=f"{side}_forearm_rail"))
        accent_parts.append(_place(limb_rail, x=sign * thigh_x * 0.92, y=shin_y, z=0.108, rz=1.5 * sign, name=f"{side}_shin_rail"))
        accent_names.extend([f"{side}_forearm_rail", f"{side}_shin_rail"])

    primary = combine(primary_parts, name="sentinel_rigid_armor_primary_v0_1")
    accent = combine(accent_parts, name="sentinel_rigid_armor_accent_v0_1")
    primary_topology = _closed_report(primary)
    accent_topology = _closed_report(accent)
    primary_uv = box_project_world(primary, world_units_per_tile=0.12)
    accent_uv = box_project_world(accent, world_units_per_tile=0.08)
    primary_uv_report = validate_uv(primary, primary_uv)
    accent_uv_report = validate_uv(accent, accent_uv)
    if primary_uv_report["status"] != "pass" or accent_uv_report["status"] != "pass":
        raise ValueError(f"armor UV invalid: primary={primary_uv_report} accent={accent_uv_report}")

    evidence: dict[str, object] = {
        "schema": SCHEMA,
        "body_bounds_m": {"min": list(lo), "max": list(hi), "height": height, "half_width": half_width},
        "anchors_m": {
            "chest_y": chest_y,
            "shoulder_y": shoulder_y,
            "forearm_y": forearm_y,
            "hip_y": hip_y,
            "thigh_y": thigh_y,
            "knee_y": knee_y,
            "shin_y": shin_y,
            "chest_front_z": chest_front_z,
            "chest_back_z": chest_back_z,
        },
        "primary_components": primary_names,
        "accent_components": accent_names,
        "primary_component_count": len(primary_parts),
        "accent_component_count": len(accent_parts),
        "primary_topology": primary_topology,
        "accent_topology": accent_topology,
        "primary_uv_validation": primary_uv_report,
        "accent_uv_validation": accent_uv_report,
        "chest_detail_level": chest_detail.level,
        "chest_detail_features": list(chest_detail.semantic_features),
        "truth": {
            "body_grounded": True,
            "production_armor_claim": False,
            "rig_deformation_claim": False,
            "notes": [
                "Armor anchors are derived from the complete human body bounds and chest surface depth rather than a detached prefab coordinate frame.",
                "This pass establishes a readable rigid silhouette and semantic armor regions; production fit still requires pose/deformation clearance and collision evidence.",
                "The chest/back reuse Forge-native hard-surface construction mechanisms, not copied third-party armor geometry."
            ],
        },
    }
    return primary, primary_uv, accent, accent_uv, evidence


def write_sentinel_armor_materials(output: str | Path, *, size: int = 256, seed: int = 93021) -> dict[str, object]:
    root = Path(output)
    primary = write_painted_metal(
        root / "primary",
        size=size,
        seed=seed,
        spec=PaintedMetalSpec(
            paint_rgb=(48, 58, 64), metal_rgb=(125, 132, 136),
            paint_roughness=0.40, metal_roughness=0.25, wear=0.16,
            scratches=10, grain_scale=34.0,
            height_grain_amplitude=0.035, height_broad_amplitude=0.018,
            height_scratch_depth=0.075, height_pit_depth=0.045,
            pit_wear_strength=0.22, base_grain_variation=0.08,
            roughness_grain_variation=0.045, normal_strength=2.0,
        ),
    )
    accent = write_painted_metal(
        root / "accent",
        size=size,
        seed=seed + 1709,
        spec=PaintedMetalSpec(
            paint_rgb=(23, 28, 31), metal_rgb=(145, 149, 151),
            paint_roughness=0.34, metal_roughness=0.22, wear=0.28,
            scratches=14, grain_scale=40.0,
            height_grain_amplitude=0.030, height_broad_amplitude=0.014,
            height_scratch_depth=0.070, height_pit_depth=0.040,
            pit_wear_strength=0.26, base_grain_variation=0.07,
            roughness_grain_variation=0.040, normal_strength=1.8,
        ),
    )
    return {"schema": "axm.game-assets.sentinel-armor-material-set.v0.1", "primary": primary, "accent": accent}


if __name__ == "__main__":
    import argparse
    from native_hm08_undersuit import _load_identity_body

    parser = argparse.ArgumentParser()
    parser.add_argument("output", nargs="?", default="build/hm08-sentinel-armor")
    parser.add_argument("--texture-size", type=int, default=256)
    args = parser.parse_args()
    body_m, _body_uv, _state = _load_identity_body()
    primary, primary_uv, accent, accent_uv, evidence = build_sentinel_rigid_armor(body_m)
    material = write_sentinel_armor_materials(Path(args.output) / "textures", size=args.texture_size)
    Path(args.output).mkdir(parents=True, exist_ok=True)
    packet = {
        "evidence": evidence,
        "material": material,
        "primary": {"vertices": len(primary.vertices), "faces": len(primary.faces), "uvs": len(primary_uv.uvs)},
        "accent": {"vertices": len(accent.vertices), "faces": len(accent.faces), "uvs": len(accent_uv.uvs)},
    }
    (Path(args.output) / "armor.json").write_text(json.dumps(packet, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(packet, indent=2))
