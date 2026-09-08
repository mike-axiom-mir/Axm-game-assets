#!/usr/bin/env python3
"""Body-grounded tactical boot rubber structure for Sentinel-01.

The source-derived boot upper follows the human foot closely, which preserves
fit but also preserves an exposed-toe silhouette. This organ keeps that upper
and its source UV truth intact while adding closed rubber toe bumpers around the
forefoot and combining them with the already-proven soles. It is a replaceable
boot construction layer, not a mutation of human topology.
"""
from __future__ import annotations

from native_geometry import Mesh, bounds, combine, topology_report
from native_modeling import make_chamfered_box, place
from native_uv import UVMap, box_project_world, validate_uv

SCHEMA = "axm.game-assets.hm08-boot-rubber-structure.v0.1"


def build_hm08_boot_rubber_structure(
    body_m: Mesh,
    soles: Mesh,
    *,
    boot_height_fraction: float = 0.10,
) -> tuple[Mesh, UVMap, dict[str, object]]:
    lo, hi = bounds(body_m)
    height = hi[1] - lo[1]
    boot_top_y = lo[1] + height * boot_height_fraction
    foot_points = [point for point in body_m.vertices if point[1] <= boot_top_y]
    if not foot_points:
        raise ValueError("boot structure found no source foot points")

    toe_parts: list[Mesh] = []
    side_evidence: dict[str, object] = {}
    for side, sign in (("left", -1.0), ("right", 1.0)):
        points = [point for point in foot_points if point[0] * sign > 0.0]
        if not points:
            raise ValueError(f"boot structure found no {side} foot points")
        xs = [p[0] for p in points]
        ys = [p[1] for p in points]
        zs = [p[2] for p in points]
        source_width = max(xs) - min(xs)
        source_depth = max(zs) - min(zs)
        source_height = max(ys) - min(ys)

        toe_width = source_width + 0.026
        toe_depth = min(0.125, max(0.090, source_depth * 0.47))
        toe_height = min(0.076, max(0.058, source_height * 0.43))
        toe_front_margin = 0.014
        x_center = (min(xs) + max(xs)) * 0.5
        z_center = max(zs) + toe_front_margin - toe_depth * 0.5
        y_center = lo[1] + 0.012 + toe_height * 0.5
        chamfer = min(0.010, toe_height * 0.16, toe_width * 0.08, toe_depth * 0.08)

        toe = make_chamfered_box(toe_width, toe_height, toe_depth, chamfer, name=f"{side}_boot_toe_bumper")
        toe = place(toe, x=x_center, y=y_center, z=z_center, name=f"{side}_boot_toe_bumper")
        toe_parts.append(toe)
        side_evidence[side] = {
            "source_width_m": source_width,
            "source_depth_m": source_depth,
            "source_height_m": source_height,
            "toe_width_m": toe_width,
            "toe_depth_m": toe_depth,
            "toe_height_m": toe_height,
            "toe_chamfer_m": chamfer,
            "toe_center_m": [x_center, y_center, z_center],
            "toe_front_margin_m": toe_front_margin,
        }

    rubber = combine([soles, *toe_parts], name="sentinel_boot_rubber_structure_v0_1")
    topology = topology_report(rubber)
    if topology["invalid_indices"] or topology["degenerate_faces"] or topology["nonmanifold_edges"]:
        raise ValueError(f"boot rubber structure topology invalid: {topology}")
    uvmap = box_project_world(rubber, world_units_per_tile=0.07)
    uv_report = validate_uv(rubber, uvmap)
    if uv_report["status"] != "pass":
        raise ValueError(f"boot rubber structure UV invalid: {uv_report}")

    evidence: dict[str, object] = {
        "schema": SCHEMA,
        "boot_height_fraction": boot_height_fraction,
        "boot_top_y_m": boot_top_y,
        "toe_component_count": len(toe_parts),
        "rubber_component_count": 1 + len(toe_parts),
        "side_evidence": side_evidence,
        "topology": topology,
        "uv_validation": uv_report,
        "truth": {
            "body_grounded": True,
            "canonical_body_mutated": False,
            "source_boot_upper_replaced": False,
            "production_boot_claim": False,
            "notes": [
                "Real Godot evidence showed that a fitted source-foot shell plus sole still read as human toes; a tactical boot needs a constructed forefoot silhouette.",
                "Toe bumpers derive width/depth/height from each real source foot region and overlap the source-derived textile upper without changing body vertices.",
                "Sole tread, toe-panel seams, heel counter and deformation remain later boot-fidelity gates."
            ],
        },
    }
    return rubber, uvmap, evidence
