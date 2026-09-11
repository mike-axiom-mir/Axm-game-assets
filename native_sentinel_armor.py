#!/usr/bin/env python3
"""Source-fitted semantic Sentinel armor v0.1.

This module builds an original rigid armor silhouette over the proven complete
human + graphite undersuit substrate. Armor components remain separate source
state. Placement is derived from the actual Sentinel body geometry and every
primary plate records conservative body clearance before engine delivery.

This is a first manufactured silhouette pass, not a final hero-armor claim.
"""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from native_geometry import Mesh, bounds, combine, topology_report, triangulate
from native_hm08_undersuit import _load_identity_body
from native_modeling import extrude_polygon, make_chamfered_box, make_cylinder
from native_multi_gltf import MaterialPrimitive, write_multi_gltf
from native_pbr import PaintedMetalSpec, write_painted_metal
from native_uv import box_project_world, validate_uv

SCHEMA = "axm.game-assets.sentinel-armor.v0.1"
ASSET_NAME = "sentinel_armor_v0_1"
MIN_BODY_CLEARANCE_M = 0.0070
UNDERSUIT_OFFSET_M = 0.0022


@dataclass(frozen=True, slots=True)
class ArmorComponent:
    name: str
    role: str
    material_group: str
    mesh: Mesh
    fit_axis: str
    paired_with: str | None = None


def _sha(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _rotate_xyz(mesh: Mesh, *, rx: float = 0.0, ry: float = 0.0, rz: float = 0.0, name: str | None = None) -> Mesh:
    cx, sx = math.cos(rx), math.sin(rx)
    cy, sy = math.cos(ry), math.sin(ry)
    cz, sz = math.cos(rz), math.sin(rz)
    out = []
    for x, y, z in mesh.vertices:
        # X
        y, z = y * cx - z * sx, y * sx + z * cx
        # Y
        x, z = x * cy + z * sy, -x * sy + z * cy
        # Z
        x, y = x * cz - y * sz, x * sz + y * cz
        out.append((x, y, z))
    return Mesh(name or mesh.name, out, list(mesh.faces))


def _translate(mesh: Mesh, x: float, y: float, z: float, *, name: str | None = None) -> Mesh:
    return Mesh(name or mesh.name, [(px + x, py + y, pz + z) for px, py, pz in mesh.vertices], list(mesh.faces))


def _tapered_panel(bottom_width: float, top_width: float, height: float, depth: float, *, name: str) -> Mesh:
    if min(bottom_width, top_width, height, depth) <= 0.0:
        raise ValueError("panel dimensions must be positive")
    hb = bottom_width * 0.5
    ht = top_width * 0.5
    hh = height * 0.5
    chamfer = min(bottom_width, top_width, height) * 0.08
    points = [
        (-hb + chamfer, -hh),
        (hb - chamfer, -hh),
        (hb, -hh + chamfer),
        (ht, hh - chamfer),
        (ht - chamfer, hh),
        (-ht + chamfer, hh),
        (-ht, hh - chamfer),
        (-hb, -hh + chamfer),
    ]
    return extrude_polygon(points, depth, name=name)


def _band_points(
    body: Mesh,
    *,
    y_min: float,
    y_max: float,
    x_min: float | None = None,
    x_max: float | None = None,
) -> list[tuple[float, float, float]]:
    rows = []
    for point in body.vertices:
        x, y, _z = point
        if y < y_min or y > y_max:
            continue
        if x_min is not None and x < x_min:
            continue
        if x_max is not None and x > x_max:
            continue
        rows.append(point)
    if not rows:
        raise ValueError(f"body band is empty y=[{y_min},{y_max}] x=[{x_min},{x_max}]")
    return rows


def _mean(values: Iterable[float]) -> float:
    rows = list(values)
    if not rows:
        raise ValueError("cannot average empty values")
    return sum(rows) / len(rows)


def _projected_body_points(body: Mesh, component: Mesh, *, margin: float = 0.012) -> list[tuple[float, float, float]]:
    lo, hi = bounds(component)
    rows = [
        point for point in body.vertices
        if lo[0] - margin <= point[0] <= hi[0] + margin
        and lo[1] - margin <= point[1] <= hi[1] + margin
    ]
    return rows or list(body.vertices)


def _clearance(body: Mesh, component: Mesh, fit_axis: str) -> float:
    rows = _projected_body_points(body, component)
    lo, hi = bounds(component)
    if fit_axis == "front_z":
        return lo[2] - max(point[2] for point in rows)
    if fit_axis == "back_z":
        return min(point[2] for point in rows) - hi[2]
    raise ValueError(f"unsupported fit axis {fit_axis}")


def _place_front(body: Mesh, mesh: Mesh, *, x: float, y: float, clearance_m: float, name: str) -> tuple[Mesh, float]:
    rotated = mesh
    local = _translate(rotated, x, y, 0.0, name=name)
    rows = _projected_body_points(body, local)
    body_front = max(point[2] for point in rows)
    lo, _hi = bounds(local)
    placed = _translate(local, 0.0, 0.0, body_front + clearance_m - lo[2], name=name)
    return placed, _clearance(body, placed, "front_z")


def _place_back(body: Mesh, mesh: Mesh, *, x: float, y: float, clearance_m: float, name: str) -> tuple[Mesh, float]:
    local = _translate(mesh, x, y, 0.0, name=name)
    rows = _projected_body_points(body, local)
    body_back = min(point[2] for point in rows)
    _lo, hi = bounds(local)
    placed = _translate(local, 0.0, 0.0, body_back - clearance_m - hi[2], name=name)
    return placed, _clearance(body, placed, "back_z")


def _arm_axis(body: Mesh, side: int, *, shoulder_y: float) -> tuple[float, float, float]:
    if side not in (-1, 1):
        raise ValueError("side must be -1 or +1")
    side_rows = [point for point in body.vertices if point[0] * side > 0.20 and point[1] > 0.05]
    if len(side_rows) < 20:
        raise ValueError("insufficient arm source points")
    outer_x = max(point[0] * side for point in side_rows)
    target_abs_x = 0.30 + (outer_x - 0.30) * 0.52
    target_x = target_abs_x * side
    local = [point for point in side_rows if abs(point[0] - target_x) <= 0.045]
    if not local:
        local = side_rows
    y = _mean(point[1] for point in local)
    dx = target_x - side * 0.225
    dy = y - shoulder_y
    angle = math.atan2(dy, dx) - (math.pi * 0.5)
    return target_x, y, angle


def _leg_center(body: Mesh, side: int, *, y_min: float, y_max: float) -> tuple[float, float, float]:
    rows = _band_points(body, y_min=y_min, y_max=y_max)
    rows = [point for point in rows if point[0] * side > 0.015]
    if not rows:
        raise ValueError("leg band contains no side points")
    x = _mean(point[0] for point in rows)
    y = (y_min + y_max) * 0.5
    front = max(point[2] for point in rows if abs(point[0] - x) < 0.09) if any(abs(point[0] - x) < 0.09 for point in rows) else max(point[2] for point in rows)
    return x, y, front


def build_sentinel_armor(body: Mesh | None = None) -> tuple[list[ArmorComponent], dict[str, object]]:
    if body is None:
        body, _body_uv, _target_state = _load_identity_body()
    lo, hi = bounds(body)
    if hi[1] - lo[1] < 1.5:
        raise ValueError("Sentinel armor expects the complete human body in meters")

    # Body-derived landmarks. These are proportions/fit anchors, not skeleton joints.
    chest_y = hi[1] - 0.405
    shoulder_y = hi[1] - 0.335
    chest_band = _band_points(body, y_min=chest_y - 0.16, y_max=chest_y + 0.16, x_min=-0.30, x_max=0.30)
    torso_half_width = max(abs(point[0]) for point in chest_band)
    chest_width = min(0.37, max(0.285, torso_half_width * 1.48))

    components: list[ArmorComponent] = []
    fit_rows: dict[str, dict[str, float | str]] = {}

    def front_component(name: str, role: str, mesh: Mesh, *, x: float, y: float, clearance: float, material: str = "coated") -> Mesh:
        placed, measured = _place_front(body, mesh, x=x, y=y, clearance_m=clearance, name=name)
        fit_rows[name] = {"fit_axis": "front_z", "requested_clearance_m": clearance, "measured_body_clearance_m": measured}
        components.append(ArmorComponent(name, role, material, placed, "front_z"))
        return placed

    def back_component(name: str, role: str, mesh: Mesh, *, x: float, y: float, clearance: float, material: str = "coated") -> Mesh:
        placed, measured = _place_back(body, mesh, x=x, y=y, clearance_m=clearance, name=name)
        fit_rows[name] = {"fit_axis": "back_z", "requested_clearance_m": clearance, "measured_body_clearance_m": measured}
        components.append(ArmorComponent(name, role, material, placed, "back_z"))
        return placed

    chest = _tapered_panel(chest_width * 0.72, chest_width, 0.265, 0.034, name="sternum_shell")
    chest_mesh = front_component("sternum_core", "chest_sternum_core", chest, x=0.0, y=chest_y, clearance=0.010)

    back = _tapered_panel(chest_width * 0.62, chest_width * 0.82, 0.305, 0.030, name="spine_shell")
    back_mesh = back_component("spine_core", "back_spine_core", back, x=0.0, y=chest_y - 0.01, clearance=0.009)

    # Paired shoulder plates: a shallow yaw + roll gives a pauldron read rather
    # than a rectangular plate copied onto the torso.
    for side, label in ((-1, "left"), (1, "right")):
        shoulder = _tapered_panel(0.145, 0.195, 0.115, 0.030, name=f"{label}_shoulder_shell")
        shoulder = _rotate_xyz(shoulder, ry=side * math.radians(18.0), rz=-side * math.radians(9.0), name=shoulder.name)
        placed = front_component(
            f"{label}_shoulder",
            "shoulder_plate",
            shoulder,
            x=side * min(0.245, torso_half_width * 1.02),
            y=shoulder_y,
            clearance=0.011,
        )
        # Replace immutable record with pairing metadata.
        components[-1] = ArmorComponent(components[-1].name, components[-1].role, components[-1].material_group, placed, components[-1].fit_axis, f"{'right' if label == 'left' else 'left'}_shoulder")

    # Forearm plates follow the actual source-arm direction in the XY plane.
    for side, label in ((-1, "left"), (1, "right")):
        x, y, angle = _arm_axis(body, side, shoulder_y=shoulder_y)
        forearm = _tapered_panel(0.068, 0.092, 0.205, 0.024, name=f"{label}_forearm_shell")
        forearm = _rotate_xyz(forearm, rz=angle, name=forearm.name)
        placed = front_component(f"{label}_forearm", "forearm_guard", forearm, x=x, y=y, clearance=0.0085)
        components[-1] = ArmorComponent(components[-1].name, components[-1].role, components[-1].material_group, placed, components[-1].fit_axis, f"{'right' if label == 'left' else 'left'}_forearm")

    # Leg protection remains vertically readable and leaves knee articulation
    # gaps between thigh and shin shells.
    thigh_band = (-0.31, -0.08)
    shin_band = (-0.69, -0.44)
    for side, label in ((-1, "left"), (1, "right")):
        tx, ty, _ = _leg_center(body, side, y_min=thigh_band[0], y_max=thigh_band[1])
        thigh = _tapered_panel(0.090, 0.125, 0.225, 0.026, name=f"{label}_thigh_shell")
        placed = front_component(f"{label}_thigh", "thigh_guard", thigh, x=tx, y=ty, clearance=0.0085)
        components[-1] = ArmorComponent(components[-1].name, components[-1].role, components[-1].material_group, placed, components[-1].fit_axis, f"{'right' if label == 'left' else 'left'}_thigh")

        sx, sy, _ = _leg_center(body, side, y_min=shin_band[0], y_max=shin_band[1])
        shin = _tapered_panel(0.082, 0.108, 0.245, 0.025, name=f"{label}_shin_shell")
        placed = front_component(f"{label}_shin", "shin_guard", shin, x=sx, y=sy, clearance=0.0080)
        components[-1] = ArmorComponent(components[-1].name, components[-1].role, components[-1].material_group, placed, components[-1].fit_axis, f"{'right' if label == 'left' else 'left'}_shin")

    # Biomechanical interface pieces sit on top of the primary armor and use a
    # separate exposed-metal material group.
    chest_lo, chest_hi = bounds(chest_mesh)
    sternum_channel = make_chamfered_box(0.052, 0.165, 0.018, 0.010, name="sternum_interface")
    sternum_channel = _translate(
        sternum_channel,
        0.0,
        chest_y - 0.005,
        chest_hi[2] + 0.011,
        name="sternum_interface",
    )
    components.append(ArmorComponent("sternum_interface", "biomechanical_interface", "mechanical", sternum_channel, "front_z"))
    fit_rows["sternum_interface"] = {"fit_axis": "front_z", "requested_clearance_m": 0.010, "measured_body_clearance_m": _clearance(body, sternum_channel, "front_z")}

    back_lo, _back_hi = bounds(back_mesh)
    spine_channel = make_chamfered_box(0.045, 0.205, 0.016, 0.008, name="spine_interface")
    _sp_lo, sp_hi = bounds(spine_channel)
    spine_channel = _translate(
        spine_channel,
        0.0,
        chest_y - 0.015,
        back_lo[2] - 0.010 - sp_hi[2],
        name="spine_interface",
    )
    components.append(ArmorComponent("spine_interface", "biomechanical_interface", "mechanical", spine_channel, "back_z"))
    fit_rows["spine_interface"] = {"fit_axis": "back_z", "requested_clearance_m": 0.009, "measured_body_clearance_m": _clearance(body, spine_channel, "back_z")}

    # Small mechanical ports break up the chest core without becoming the
    # primary silhouette language.
    for side, label in ((-1, "left"), (1, "right")):
        port = make_cylinder(0.018, 0.016, segments=16, name=f"{label}_chest_port")
        port = _translate(port, side * chest_width * 0.19, chest_y - 0.070, chest_hi[2] + 0.012, name=port.name)
        components.append(ArmorComponent(f"{label}_chest_port", "biomechanical_port", "mechanical", port, "front_z", f"{'right' if label == 'left' else 'left'}_chest_port"))
        fit_rows[f"{label}_chest_port"] = {"fit_axis": "front_z", "requested_clearance_m": 0.010, "measured_body_clearance_m": _clearance(body, port, "front_z")}

    primary = [component for component in components if component.material_group == "coated"]
    mechanical = [component for component in components if component.material_group == "mechanical"]
    failures = []
    for component in components:
        report = topology_report(component.mesh)
        if report["invalid_indices"] or report["degenerate_faces"] or report["nonmanifold_edges"]:
            failures.append(f"{component.name} topology invalid: {report}")
        measured = float(fit_rows[component.name]["measured_body_clearance_m"])
        if measured < MIN_BODY_CLEARANCE_M:
            failures.append(f"{component.name} clearance {measured:.6f}m below {MIN_BODY_CLEARANCE_M:.6f}m")
    if len(primary) < 10:
        failures.append("expected at least ten semantic primary armor components")
    if len(mechanical) < 4:
        failures.append("expected at least four mechanical interface components")

    all_mesh = combine([component.mesh for component in components], name="sentinel_armor_all")
    tri = triangulate(all_mesh)
    evidence: dict[str, object] = {
        "schema": SCHEMA,
        "status": "pass" if not failures else "fail",
        "failures": failures,
        "source_body": {
            "vertices": len(body.vertices),
            "faces": len(body.faces),
            "bounds_m": [list(lo), list(hi)],
        },
        "minimum_body_clearance_m": MIN_BODY_CLEARANCE_M,
        "undersuit_offset_m": UNDERSUIT_OFFSET_M,
        "minimum_clearance_over_undersuit_m": MIN_BODY_CLEARANCE_M - UNDERSUIT_OFFSET_M,
        "component_count": len(components),
        "primary_component_count": len(primary),
        "mechanical_component_count": len(mechanical),
        "triangles": len(tri.faces),
        "fit": fit_rows,
        "components": [
            {
                "name": component.name,
                "role": component.role,
                "material_group": component.material_group,
                "paired_with": component.paired_with,
                "fit_axis": component.fit_axis,
                "vertices": len(component.mesh.vertices),
                "faces": len(component.mesh.faces),
                "triangles": len(triangulate(component.mesh).faces),
                "bounds_m": [list(row) for row in bounds(component.mesh)],
            }
            for component in components
        ],
        "truth": {
            "original_design": True,
            "source_fitted": True,
            "production_armor_claim": False,
            "notes": [
                "Primary armor scale/placement is derived from the current Sentinel body rather than copied from the old standalone rectangular plate proof.",
                "The first pass prioritizes chest/back/shoulder/limb hierarchy and clearance. It is not final tailoring, deformation clearance or hero microdetail.",
                "Paired components remain separate canonical source state for later variants and damage edits.",
                "Godot front/three-quarter/profile evidence is required before visual promotion.",
            ],
        },
    }
    if failures:
        raise ValueError(f"Sentinel armor native gates failed: {evidence}")
    return components, evidence


def write_sentinel_armor_package(
    output: str | Path,
    *,
    texture_size: int = 256,
    primary_seed: int = 131071,
    mechanical_seed: int = 131173,
) -> dict[str, object]:
    root = Path(output)
    root.mkdir(parents=True, exist_ok=True)
    components, evidence = build_sentinel_armor()

    primary_material = write_painted_metal(
        root / "textures" / "armor_primary",
        size=texture_size,
        seed=primary_seed,
        spec=PaintedMetalSpec(
            paint_rgb=(42, 55, 52),
            metal_rgb=(112, 118, 120),
            paint_roughness=0.40,
            metal_roughness=0.24,
            wear=0.15,
            scratches=10,
            grain_scale=34.0,
            height_grain_amplitude=0.026,
            height_broad_amplitude=0.012,
            height_scratch_depth=0.055,
            height_pit_depth=0.035,
            pit_wear_strength=0.25,
            base_grain_variation=0.055,
            roughness_grain_variation=0.045,
            normal_strength=1.8,
        ),
    )
    mechanical_material = write_painted_metal(
        root / "textures" / "armor_mechanical",
        size=texture_size,
        seed=mechanical_seed,
        spec=PaintedMetalSpec(
            paint_rgb=(27, 31, 32),
            metal_rgb=(130, 136, 139),
            paint_roughness=0.34,
            metal_roughness=0.20,
            wear=0.32,
            scratches=14,
            grain_scale=42.0,
            height_grain_amplitude=0.020,
            height_broad_amplitude=0.010,
            height_scratch_depth=0.050,
            height_pit_depth=0.030,
            pit_wear_strength=0.32,
            base_grain_variation=0.045,
            roughness_grain_variation=0.040,
            normal_strength=1.6,
        ),
    )

    primitives = []
    uv_receipts = {}
    for component in components:
        uv = box_project_world(component.mesh, world_units_per_tile=0.16)
        uv_report = validate_uv(component.mesh, uv)
        if uv_report["status"] != "pass":
            raise ValueError(f"armor UV invalid for {component.name}: {uv_report}")
        uv_receipts[component.name] = uv_report
        if component.material_group == "coated":
            base = "textures/armor_primary/base_color.png"
            normal = "textures/armor_primary/normal.png"
            orm = "textures/armor_primary/orm.png"
            material_name = f"Sentinel_Coated_{component.name}"
        else:
            base = "textures/armor_mechanical/base_color.png"
            normal = "textures/armor_mechanical/normal.png"
            orm = "textures/armor_mechanical/orm.png"
            material_name = f"Sentinel_Mechanical_{component.name}"
        primitives.append(
            MaterialPrimitive(
                component.mesh,
                uv,
                material_name,
                base,
                normal,
                orm,
                metallic_factor=1.0,
                roughness_factor=1.0,
            )
        )

    delivery = write_multi_gltf(primitives, root, name=ASSET_NAME)
    acceptance = {
        "native_fit_green": evidence["status"] == "pass",
        "semantic_component_count": evidence["component_count"] >= 14,
        "primary_silhouette_components": evidence["primary_component_count"] >= 10,
        "mechanical_interface_components": evidence["mechanical_component_count"] >= 4,
        "clearance_over_undersuit": evidence["minimum_clearance_over_undersuit_m"] >= 0.004,
        "all_uvs_valid": all(row["status"] == "pass" for row in uv_receipts.values()),
        "one_gltf_primitive_per_semantic_component": delivery["primitive_count"] == evidence["component_count"],
        "material_count_matches_components": delivery["material_count"] == evidence["component_count"],
        "gltf_structural_valid": delivery["validation"]["status"] == "pass",
    }
    manifest: dict[str, object] = {
        "schema": SCHEMA,
        "asset": ASSET_NAME,
        "candidate_role": "sentinel_rigid_armor_silhouette_v0_1",
        "armor": evidence,
        "uv_validation": uv_receipts,
        "materials": {
            "primary": primary_material,
            "mechanical": mechanical_material,
        },
        "delivery": delivery,
        "acceptance": acceptance,
        "truth": {
            "visual_promotion": False,
            "production_armor_claim": False,
            "notes": [
                "Native clearance and structural gates only prove the armor can be manufactured and placed without the known undersuit/body envelope.",
                "Real Godot whole-character evidence decides whether the silhouette and manufactured language are actually useful.",
            ],
        },
    }
    payload = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8")
    (root / "armor-package.json").write_bytes(payload)
    manifest["manifest_sha256"] = _sha(payload)
    if not all(acceptance.values()):
        raise ValueError(f"Sentinel armor package failed: {acceptance}")
    return manifest


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("output", nargs="?", default="build/sentinel-armor")
    parser.add_argument("--texture-size", type=int, default=256)
    args = parser.parse_args()
    result = write_sentinel_armor_package(args.output, texture_size=args.texture_size)
    print(json.dumps({"acceptance": result["acceptance"], "armor": result["armor"], "delivery": result["delivery"]}, indent=2))
