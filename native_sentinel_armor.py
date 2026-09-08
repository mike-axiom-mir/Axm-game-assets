#!/usr/bin/env python3
"""Deterministic first-pass Sentinel rigid armor fitted to the complete hm08 body.

This organ is intentionally a silhouette/manufacturing layer, not final hero armor.
It derives semantic anchors from the actual body bounds and front/back surface
samples, then builds separate closed rigid components over the proven undersuit.
Each component remains independently addressable for later edit/damage/variant use.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from native_geometry import Mesh, bounds, combine, topology_report
from native_modeling import extrude_polygon, make_chamfered_box, place
from native_pbr import PaintedMetalSpec, write_painted_metal

SCHEMA = "axm.game-assets.sentinel-armor-silhouette.v0.1"


@dataclass(frozen=True, slots=True)
class ArmorPart:
    name: str
    mesh: Mesh
    role: str


def _region_z(body: Mesh, *, x_abs_max: float, y_min: float, y_max: float, front: bool) -> float:
    rows = [
        z for x, y, z in body.vertices
        if abs(x) <= x_abs_max and y_min <= y <= y_max
    ]
    if not rows:
        raise ValueError("body region produced no surface samples")
    return max(rows) if front else min(rows)


def _trapezoid(width_top: float, width_bottom: float, height: float, corner: float) -> list[tuple[float, float]]:
    ht = height * 0.5
    wt = width_top * 0.5
    wb = width_bottom * 0.5
    c = min(corner, height * 0.18, width_bottom * 0.18)
    return [
        (-wb + c, -ht), (wb - c, -ht), (wb, -ht + c),
        (wt, ht - c), (wt - c, ht), (-wt + c, ht),
        (-wt, ht - c), (-wb, -ht + c),
    ]


def build_sentinel_armor(body_m: Mesh, *, clearance_m: float = 0.006) -> tuple[list[ArmorPart], dict[str, object]]:
    if clearance_m <= 0 or clearance_m > 0.02:
        raise ValueError("armor clearance must be >0 and <=20 mm")
    lo, hi = bounds(body_m)
    height = hi[1] - lo[1]
    width = hi[0] - lo[0]
    if not (1.4 <= height <= 2.1):
        raise ValueError(f"unexpected human height for armor fitting: {height}")

    # Semantic vertical bands derived as fractions of this exact body height.
    chest_y = lo[1] + height * 0.68
    upper_chest_min = lo[1] + height * 0.60
    upper_chest_max = lo[1] + height * 0.78
    pelvis_y = lo[1] + height * 0.47
    shin_y = lo[1] + height * 0.22

    torso_half_width = width * 0.20
    front_z = _region_z(body_m, x_abs_max=torso_half_width, y_min=upper_chest_min, y_max=upper_chest_max, front=True)
    back_z = _region_z(body_m, x_abs_max=torso_half_width, y_min=upper_chest_min, y_max=upper_chest_max, front=False)

    parts: list[ArmorPart] = []

    chest_profile = _trapezoid(width_top=0.39, width_bottom=0.29, height=0.34, corner=0.035)
    chest = extrude_polygon(chest_profile, 0.034, name="sentinel_chest_primary")
    chest = place(chest, y=chest_y, z=front_z + clearance_m + 0.017)
    parts.append(ArmorPart("chest_primary", chest, "front_torso_protection"))

    sternum = make_chamfered_box(0.115, 0.245, 0.022, 0.016, name="sentinel_sternum_core")
    sternum = place(sternum, y=chest_y + 0.005, z=front_z + clearance_m + 0.045)
    parts.append(ArmorPart("sternum_core", sternum, "biomechanical_front_core"))

    back_profile = _trapezoid(width_top=0.34, width_bottom=0.27, height=0.31, corner=0.032)
    back = extrude_polygon(back_profile, 0.030, name="sentinel_back_primary")
    back = place(back, y=chest_y - 0.008, z=back_z - clearance_m - 0.015)
    parts.append(ArmorPart("back_primary", back, "back_torso_protection"))

    spine = make_chamfered_box(0.064, 0.28, 0.025, 0.010, name="sentinel_spine_core")
    spine = place(spine, y=chest_y - 0.02, z=back_z - clearance_m - 0.040)
    parts.append(ArmorPart("spine_core", spine, "rear_biomechanical_spine"))

    shoulder_y = lo[1] + height * 0.735
    for side, sign in (("left", -1.0), ("right", 1.0)):
        shoulder = make_chamfered_box(0.145, 0.115, 0.105, 0.026, name=f"sentinel_{side}_shoulder")
        shoulder = place(shoulder, x=sign * width * 0.315, y=shoulder_y, z=(front_z + back_z) * 0.5 + 0.010)
        parts.append(ArmorPart(f"{side}_shoulder", shoulder, "shoulder_protection"))

    pelvis = make_chamfered_box(0.285, 0.13, 0.085, 0.026, name="sentinel_pelvis_guard")
    pelvis_front = _region_z(body_m, x_abs_max=0.18, y_min=pelvis_y - 0.08, y_max=pelvis_y + 0.08, front=True)
    pelvis = place(pelvis, y=pelvis_y, z=pelvis_front + clearance_m + 0.032)
    parts.append(ArmorPart("pelvis_guard", pelvis, "central_pelvis_protection"))

    # Legs are near vertical in the canonical hm08 stance, so front shin shells
    # can use simple chamfered plates without inventing an armature-space frame.
    for side, sign in (("left", -1.0), ("right", 1.0)):
        x_center = sign * width * 0.105
        leg_rows = [
            z for x, y, z in body_m.vertices
            if abs(x - x_center) <= 0.10 and shin_y - 0.16 <= y <= shin_y + 0.16
        ]
        shin_front = max(leg_rows) if leg_rows else front_z * 0.5
        shin = make_chamfered_box(0.115, 0.29, 0.042, 0.020, name=f"sentinel_{side}_shin")
        shin = place(shin, x=x_center, y=shin_y, z=shin_front + clearance_m + 0.021)
        parts.append(ArmorPart(f"{side}_shin", shin, "front_shin_protection"))

    combined = combine([part.mesh for part in parts], name="sentinel_armor_silhouette_v0_1")
    report = topology_report(combined)
    if report["invalid_indices"] or report["degenerate_faces"] or report["nonmanifold_edges"]:
        raise ValueError(f"armor structural failure: {report}")

    evidence = {
        "schema": SCHEMA,
        "source_body_bounds_m": {"min": list(lo), "max": list(hi)},
        "source_body_height_m": height,
        "source_body_width_m": width,
        "clearance_m": clearance_m,
        "surface_anchors": {"front_chest_z_m": front_z, "back_chest_z_m": back_z},
        "parts": [{"name": p.name, "role": p.role, "topology": topology_report(p.mesh), "bounds": bounds(p.mesh)} for p in parts],
        "combined_topology": report,
        "truth": {
            "source_fitted": True,
            "hero_armor_claim": False,
            "deformation_ready_claim": False,
            "notes": [
                "v0.1 is the first rigid silhouette pass over the proven fitted undersuit, not final hero armor.",
                "Chest/back/pelvis depth anchors are sampled from the actual current human body rather than fixed world guesses.",
                "Shoulder and shin parts remain simple closed semantic shells until rig-space fitting and close-up manufacturing detail are proven.",
            ],
        },
    }
    return parts, evidence


def write_sentinel_armor_material(output: str | Path, *, size: int = 256, seed: int = 111021) -> dict[str, object]:
    return write_painted_metal(
        output,
        size=size,
        seed=seed,
        spec=PaintedMetalSpec(
            paint_rgb=(45, 53, 57),
            metal_rgb=(112, 119, 124),
            paint_roughness=0.39,
            metal_roughness=0.24,
            wear=0.16,
            scratches=8,
            grain_scale=34.0,
            height_grain_amplitude=0.025,
            height_broad_amplitude=0.010,
            height_scratch_depth=0.055,
            height_pit_depth=0.030,
            pit_wear_strength=0.22,
            base_grain_variation=0.055,
            roughness_grain_variation=0.035,
            normal_strength=1.6,
        ),
    )


if __name__ == "__main__":
    from native_hm08_undersuit import _load_identity_body
    body_m, _uv, _state = _load_identity_body()
    parts, evidence = build_sentinel_armor(body_m)
    root = Path("build/sentinel-armor")
    material = write_sentinel_armor_material(root / "material")
    root.mkdir(parents=True, exist_ok=True)
    (root / "armor.json").write_text(json.dumps({"evidence": evidence, "material": material}, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"parts": [p.name for p in parts], "evidence": evidence}, indent=2))
