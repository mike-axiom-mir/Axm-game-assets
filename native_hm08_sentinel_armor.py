#!/usr/bin/env python3
"""Body-grounded deterministic rigid armor for Sentinel-01 v0.2.

v0.1 proved that Forge can anchor reconstructable rigid components to the
complete hm08 human substrate, but real Godot evidence showed a prototype/toy
read: one oversized rectangular chest slab and box-like limb guards dominated
the silhouette.

v0.2 keeps the same native/material interface while changing the construction
language to segmented, anatomy-aware armor: split pectorals and clavicles,
compact sternum machinery, abdominal articulation, scapular/back protection,
and tapered limb shells. It is still a static fit proof, not a rig/deformation
or production-armor claim.
"""
from __future__ import annotations

import json
from math import cos, radians, sin
from pathlib import Path

from native_geometry import Mesh, bounds, combine, scale, topology_report, translate
from native_hardsurface import sentinel_armor_plate
from native_modeling import extrude_polygon, make_chamfered_box
from native_pbr import PaintedMetalSpec, write_painted_metal
from native_uv import UVMap, box_project_world, validate_uv

SCHEMA = "axm.game-assets.hm08-sentinel-rigid-armor.v0.2"


def _rotate_y(mesh: Mesh, degrees: float, *, name: str | None = None) -> Mesh:
    angle = radians(degrees)
    c, s = cos(angle), sin(angle)
    return Mesh(name or mesh.name, [(x * c + z * s, y, -x * s + z * c) for x, y, z in mesh.vertices], list(mesh.faces))


def _rotate_z(mesh: Mesh, degrees: float, *, name: str | None = None) -> Mesh:
    angle = radians(degrees)
    c, s = cos(angle), sin(angle)
    return Mesh(name or mesh.name, [(x * c - y * s, x * s + y * c, z) for x, y, z in mesh.vertices], list(mesh.faces))


def _place(mesh: Mesh, *, x: float = 0.0, y: float = 0.0, z: float = 0.0, rz: float = 0.0, ry: float = 0.0, name: str | None = None) -> Mesh:
    out = mesh
    if abs(ry) > 1e-12:
        out = _rotate_y(out, ry)
    if abs(rz) > 1e-12:
        out = _rotate_z(out, rz)
    return translate(out, (x, y, z), name=name)


def _tapered_plate(*, top_width: float, bottom_width: float, height: float, depth: float, corner: float, name: str) -> Mesh:
    if min(top_width, bottom_width, height, depth) <= 0.0:
        raise ValueError("tapered plate dimensions must be positive")
    if corner < 0.0:
        raise ValueError("corner must be non-negative")
    ht, hb, hh = top_width * 0.5, bottom_width * 0.5, height * 0.5
    c = min(corner, top_width * 0.18, bottom_width * 0.18, height * 0.16)
    points = [
        (-hb + c, -hh), (hb - c, -hh), (hb, -hh + c), (ht, hh - c),
        (ht - c, hh), (-ht + c, hh), (-ht, hh - c), (-hb, -hh + c),
    ]
    return extrude_polygon(points, depth, name=name)


def _region_depth(body: Mesh, *, y_center: float, y_half: float, x_center: float = 0.0, x_half: float) -> tuple[float, float]:
    points = [p for p in body.vertices if abs(p[1] - y_center) <= y_half and abs(p[0] - x_center) <= x_half]
    if not points:
        points = list(body.vertices)
    zs = [p[2] for p in points]
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

    chest_y = yf(0.690)
    collar_y = yf(0.790)
    abdomen_y = yf(0.575)
    shoulder_y = yf(0.775)
    forearm_y = yf(0.610)
    hip_y = yf(0.465)
    thigh_y = yf(0.350)
    knee_y = yf(0.245)
    shin_y = yf(0.130)
    chest_back_z, chest_front_z = _region_depth(body_m, y_center=chest_y, y_half=height * 0.105, x_half=half_width * 0.48)
    abdomen_back_z, abdomen_front_z = _region_depth(body_m, y_center=abdomen_y, y_half=height * 0.075, x_half=half_width * 0.38)

    primary_parts: list[Mesh] = []
    accent_parts: list[Mesh] = []
    primary_names: list[str] = []
    accent_names: list[str] = []

    def add_primary(name: str, mesh: Mesh) -> None:
        primary_parts.append(mesh); primary_names.append(name)

    def add_accent(name: str, mesh: Mesh) -> None:
        accent_parts.append(mesh); accent_names.append(name)

    # Segmented torso: the rejected v0.1 billboard chest is gone.
    pectoral = _tapered_plate(top_width=0.205, bottom_width=0.165, height=0.205, depth=0.042, corner=0.024, name="pectoral_plate")
    for side, sign in (("left", -1.0), ("right", 1.0)):
        add_primary(f"{side}_pectoral", _place(pectoral, x=sign * 0.105, y=chest_y + 0.025, z=chest_front_z + 0.030, rz=-4.5 * sign, name=f"{side}_pectoral"))

    sternum_source, chest_detail = sentinel_armor_plate(3)
    sternum = scale(sternum_source, (0.285, 0.265, 0.58), name="sternum_core")
    add_primary("sternum_core", _place(sternum, y=chest_y + 0.005, z=chest_front_z + 0.041, name="sternum_core"))

    collar = _tapered_plate(top_width=0.180, bottom_width=0.125, height=0.082, depth=0.034, corner=0.015, name="collar_plate")
    for side, sign in (("left", -1.0), ("right", 1.0)):
        add_primary(f"{side}_collar", _place(collar, x=sign * 0.125, y=collar_y - 0.020, z=chest_front_z + 0.018, rz=11.0 * sign, name=f"{side}_collar"))

    abdomen_plate = _tapered_plate(top_width=0.245, bottom_width=0.205, height=0.067, depth=0.028, corner=0.012, name="abdomen_leaf")
    for index, offset_y in enumerate((0.045, -0.030, -0.105)):
        leaf = scale(abdomen_plate, (1.0 - index * 0.08, 1.0, 1.0), name=f"abdomen_leaf_{index+1}")
        add_primary(f"abdomen_leaf_{index+1}", _place(leaf, y=abdomen_y + offset_y, z=abdomen_front_z + 0.022 + index * 0.0015, name=f"abdomen_leaf_{index+1}"))

    scapula = _tapered_plate(top_width=0.195, bottom_width=0.150, height=0.225, depth=0.038, corner=0.022, name="scapula_plate")
    for side, sign in (("left", -1.0), ("right", 1.0)):
        add_primary(f"{side}_scapula", _place(scapula, x=sign * 0.108, y=chest_y + 0.008, z=chest_back_z - 0.027, ry=180.0, rz=3.5 * sign, name=f"{side}_scapula"))
    back_spine_shell = _tapered_plate(top_width=0.090, bottom_width=0.070, height=0.300, depth=0.034, corner=0.012, name="back_spine_shell")
    add_primary("back_spine_shell", _place(back_spine_shell, y=chest_y - 0.018, z=chest_back_z - 0.031, ry=180.0, name="back_spine_shell"))

    # Tapered limbs preserve joint/suit gaps instead of reading as cuboids.
    shoulder_x = half_width * 0.48
    pauldron = _tapered_plate(top_width=0.155, bottom_width=0.115, height=0.135, depth=0.058, corner=0.020, name="pauldron")
    for side, sign in (("left", -1.0), ("right", 1.0)):
        add_primary(f"{side}_pauldron", _place(pauldron, x=sign * shoulder_x, y=shoulder_y, z=0.034, rz=21.0 * sign, name=f"{side}_pauldron"))

    forearm_x = half_width * 0.69
    forearm = _tapered_plate(top_width=0.090, bottom_width=0.065, height=0.220, depth=0.048, corner=0.014, name="forearm_guard")
    for side, sign in (("left", -1.0), ("right", 1.0)):
        add_primary(f"{side}_forearm_guard", _place(forearm, x=sign * forearm_x, y=forearm_y, z=0.047, rz=31.0 * sign, name=f"{side}_forearm_guard"))

    hip_x = half_width * 0.30
    hip_plate = _tapered_plate(top_width=0.110, bottom_width=0.080, height=0.155, depth=0.040, corner=0.014, name="hip_plate")
    for side, sign in (("left", -1.0), ("right", 1.0)):
        add_primary(f"{side}_hip_plate", _place(hip_plate, x=sign * hip_x, y=hip_y, z=0.056, rz=8.0 * sign, name=f"{side}_hip_plate"))

    thigh_x = half_width * 0.232
    thigh_plate = _tapered_plate(top_width=0.145, bottom_width=0.105, height=0.285, depth=0.043, corner=0.018, name="thigh_plate")
    knee_plate = _tapered_plate(top_width=0.128, bottom_width=0.110, height=0.105, depth=0.058, corner=0.021, name="knee_plate")
    shin_plate = _tapered_plate(top_width=0.112, bottom_width=0.078, height=0.300, depth=0.044, corner=0.017, name="shin_plate")
    for side, sign in (("left", -1.0), ("right", 1.0)):
        add_primary(f"{side}_thigh_plate", _place(thigh_plate, x=sign * thigh_x, y=thigh_y, z=0.091, rz=2.0 * sign, name=f"{side}_thigh_plate"))
        add_primary(f"{side}_knee_plate", _place(knee_plate, x=sign * thigh_x, y=knee_y, z=0.112, name=f"{side}_knee_plate"))
        add_primary(f"{side}_shin_plate", _place(shin_plate, x=sign * thigh_x * 0.92, y=shin_y, z=0.075, rz=1.0 * sign, name=f"{side}_shin_plate"))

    # Separate mechanical accent layer for recolor/damage/edit operations.
    sternum_rail = make_chamfered_box(0.030, 0.205, 0.018, 0.006, name="sternum_rail")
    add_accent("sternum_rail", _place(sternum_rail, y=chest_y + 0.004, z=chest_front_z + 0.079, name="sternum_rail"))
    pec_rail = make_chamfered_box(0.024, 0.145, 0.015, 0.005, name="pectoral_rail")
    for side, sign in (("left", -1.0), ("right", 1.0)):
        add_accent(f"{side}_pectoral_rail", _place(pec_rail, x=sign * 0.108, y=chest_y + 0.022, z=chest_front_z + 0.057, rz=-4.5 * sign, name=f"{side}_pectoral_rail"))

    collar_rail = make_chamfered_box(0.080, 0.018, 0.014, 0.005, name="collar_rail")
    for side, sign in (("left", -1.0), ("right", 1.0)):
        add_accent(f"{side}_collar_rail", _place(collar_rail, x=sign * 0.130, y=collar_y - 0.018, z=chest_front_z + 0.040, rz=11.0 * sign, name=f"{side}_collar_rail"))

    abdomen_rail = make_chamfered_box(0.118, 0.014, 0.013, 0.004, name="abdomen_rail")
    for index, offset_y in enumerate((0.045, -0.030, -0.105)):
        add_accent(f"abdomen_rail_{index+1}", _place(abdomen_rail, y=abdomen_y + offset_y, z=abdomen_front_z + 0.041, name=f"abdomen_rail_{index+1}"))

    back_rail = make_chamfered_box(0.028, 0.255, 0.016, 0.005, name="back_rail")
    add_accent("back_rail", _place(back_rail, y=chest_y - 0.012, z=chest_back_z - 0.057, ry=180.0, name="back_rail"))
    limb_rail = make_chamfered_box(0.022, 0.150, 0.014, 0.005, name="limb_rail")
    for side, sign in (("left", -1.0), ("right", 1.0)):
        add_accent(f"{side}_forearm_rail", _place(limb_rail, x=sign * forearm_x, y=forearm_y, z=0.075, rz=31.0 * sign, name=f"{side}_forearm_rail"))
        add_accent(f"{side}_shin_rail", _place(limb_rail, x=sign * thigh_x * 0.92, y=shin_y, z=0.101, rz=1.0 * sign, name=f"{side}_shin_rail"))

    primary = combine(primary_parts, name="sentinel_rigid_armor_primary_v0_2")
    accent = combine(accent_parts, name="sentinel_rigid_armor_accent_v0_2")
    primary_topology = _closed_report(primary)
    accent_topology = _closed_report(accent)
    primary_uv = box_project_world(primary, world_units_per_tile=0.10)
    accent_uv = box_project_world(accent, world_units_per_tile=0.065)
    primary_uv_report = validate_uv(primary, primary_uv)
    accent_uv_report = validate_uv(accent, accent_uv)
    if primary_uv_report["status"] != "pass" or accent_uv_report["status"] != "pass":
        raise ValueError(f"armor UV invalid: primary={primary_uv_report} accent={accent_uv_report}")

    evidence: dict[str, object] = {
        "schema": SCHEMA,
        "design_revision": "segmented_anatomical_v0.2",
        "body_bounds_m": {"min": list(lo), "max": list(hi), "height": height, "half_width": half_width},
        "anchors_m": {
            "chest_y": chest_y, "collar_y": collar_y, "abdomen_y": abdomen_y,
            "shoulder_y": shoulder_y, "forearm_y": forearm_y, "hip_y": hip_y,
            "thigh_y": thigh_y, "knee_y": knee_y, "shin_y": shin_y,
            "chest_front_z": chest_front_z, "chest_back_z": chest_back_z,
            "abdomen_front_z": abdomen_front_z, "abdomen_back_z": abdomen_back_z,
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
        "silhouette_intent": {
            "torso": "split pectorals + compact sternum + articulated abdomen",
            "back": "paired scapula shells + spine shell",
            "limbs": "tapered guards preserving joint/suit gaps",
            "quality_reference_class": "modern shipped hero-character readability; no proprietary design copied",
        },
        "truth": {
            "body_grounded": True,
            "production_armor_claim": False,
            "rig_deformation_claim": False,
            "copied_character_design_claim": False,
            "notes": [
                "v0.1 passed technical gates but real Godot evidence was visually rejected because an oversized rectangular chest core and boxy limb shells read as prototype/toy armor.",
                "v0.2 replaces that slab with independently reconstructable pectoral, collar, sternum, abdomen, scapula/back and tapered limb components while preserving the same body-grounded interface.",
                "The hard-surface detail mechanism is retained only on the compact sternum core where manufacturing detail is visually plausible.",
                "This is still a static silhouette/material proof. Production fit requires articulation, pose clearance, attachment, damage-state and close-up engine evidence.",
            ],
        },
    }
    return primary, primary_uv, accent, accent_uv, evidence


def write_sentinel_armor_materials(output: str | Path, *, size: int = 256, seed: int = 93021) -> dict[str, object]:
    root = Path(output)
    primary = write_painted_metal(
        root / "primary", size=size, seed=seed,
        spec=PaintedMetalSpec(
            paint_rgb=(39, 48, 54), metal_rgb=(118, 126, 131),
            paint_roughness=0.46, metal_roughness=0.28, wear=0.085,
            scratches=6, grain_scale=38.0,
            height_grain_amplitude=0.020, height_broad_amplitude=0.010,
            height_scratch_depth=0.050, height_pit_depth=0.025,
            pit_wear_strength=0.12, base_grain_variation=0.045,
            roughness_grain_variation=0.030, normal_strength=1.45,
        ),
    )
    accent = write_painted_metal(
        root / "accent", size=size, seed=seed + 1709,
        spec=PaintedMetalSpec(
            paint_rgb=(18, 23, 27), metal_rgb=(137, 143, 147),
            paint_roughness=0.38, metal_roughness=0.24, wear=0.13,
            scratches=8, grain_scale=44.0,
            height_grain_amplitude=0.018, height_broad_amplitude=0.008,
            height_scratch_depth=0.045, height_pit_depth=0.022,
            pit_wear_strength=0.14, base_grain_variation=0.040,
            roughness_grain_variation=0.026, normal_strength=1.35,
        ),
    )
    return {
        "schema": "axm.game-assets.sentinel-armor-material-set.v0.2",
        "primary": primary,
        "accent": accent,
        "truth": {"material_tuning": "reduced broad wear/noise after v0.1 Godot evidence", "production_material_claim": False},
    }


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
        "evidence": evidence, "material": material,
        "primary": {"vertices": len(primary.vertices), "faces": len(primary.faces), "uvs": len(primary_uv.uvs)},
        "accent": {"vertices": len(accent.vertices), "faces": len(accent.faces), "uvs": len(accent_uv.uvs)},
    }
    (Path(args.output) / "armor.json").write_text(json.dumps(packet, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(packet, indent=2))
