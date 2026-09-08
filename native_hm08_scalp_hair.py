#!/usr/bin/env python3
"""hm08 short-scalp-hair root selection and card state.

Scalp eligibility is derived from the repaired human head and pinned eye plane,
not the generic sphere heuristic: a crown region above the authored hairline is
combined with a behind-eye back/side region that is narrowed laterally to avoid
using outer ear geometry as hair roots. The selected canonical vertex ids feed
the generic explicit-root hair guide mechanism.
"""
from __future__ import annotations

import json
from pathlib import Path

from native_geometry import Mesh, bounds, scale
from native_hair import hair_cards_with_uv, validate_hair
from native_hair_roots import ExplicitRootHair, generate_short_hair_from_roots
from native_hm08_face_proof import DEFAULT_WEIGHTS
from native_targets import load_target, mix_targets
from native_uv import UVMap, read_obj_uv, validate_uv

SEED_ROOT = Path("seed_data/hm08_head_v0.2")
RAW_TO_M = 0.1
SCHEMA = "axm.game-assets.hm08-short-scalp-hair.v0.1"


def select_hm08_scalp_candidates(head_m: Mesh, eye_metadata: dict[str, object]) -> tuple[list[int], dict[str, float | int]]:
    lo, hi = bounds(head_m)
    eye_y = sum(float(eye_metadata["eyes"][side]["center_m"][1]) for side in ("left", "right")) * 0.5
    eye_z = sum(float(eye_metadata["eyes"][side]["center_m"][2]) for side in ("left", "right")) * 0.5
    half_width = max(abs(lo[0]), abs(hi[0]), 1e-9)

    crown_y = eye_y + 0.031
    back_side_y = eye_y - 0.012
    back_side_z_max = eye_z + 0.002
    crown_lateral_limit = half_width * 0.92
    back_lateral_limit = half_width * 0.82

    candidates: list[int] = []
    crown_count = 0
    back_side_count = 0
    for index, point in enumerate(head_m.vertices):
        x, y, z = point
        crown = y >= crown_y and abs(x) <= crown_lateral_limit
        back_side = y >= back_side_y and z <= back_side_z_max and abs(x) <= back_lateral_limit
        if crown or back_side:
            candidates.append(index)
            crown_count += int(crown)
            back_side_count += int(back_side)

    evidence = {
        "candidate_count": len(candidates),
        "crown_candidate_hits": crown_count,
        "back_side_candidate_hits": back_side_count,
        "crown_y_m": crown_y,
        "back_side_y_m": back_side_y,
        "back_side_z_max_m": back_side_z_max,
        "crown_lateral_limit_m": crown_lateral_limit,
        "back_lateral_limit_m": back_lateral_limit,
    }
    return candidates, evidence


def generate_hm08_short_scalp_hair(
    head_m: Mesh,
    *,
    eye_metadata: dict[str, object],
    guide_count: int = 256,
    segments: int = 5,
    length_m: float = 0.025,
    root_width_m: float = 0.0055,
    tip_width_m: float = 0.0009,
    root_offset_m: float = 0.0006,
    seed: int = 72081,
) -> tuple[ExplicitRootHair, Mesh, UVMap, dict[str, object]]:
    candidates, selection = select_hm08_scalp_candidates(head_m, eye_metadata)
    rooted = generate_short_hair_from_roots(
        head_m,
        candidates,
        guide_count=guide_count,
        segments=segments,
        length=length_m,
        root_width=root_width_m,
        tip_width=tip_width_m,
        root_offset=root_offset_m,
        seed=seed,
        allow_root_reuse=False,
        style="hm08_short_scalp_cards_v0.1",
    )
    validation = validate_hair(rooted.system)
    if validation["status"] != "pass":
        raise ValueError(f"hm08 scalp hair guide validation failed: {validation}")
    cards, uvmap = hair_cards_with_uv(rooted.system, name="sentinel_hm08_short_scalp_hair")
    uv_report = validate_uv(cards, uvmap)
    if uv_report["status"] != "pass":
        raise ValueError(f"hm08 scalp hair card UV failed: {uv_report}")

    selected_points = [head_m.vertices[index] for index in rooted.root_indices]
    x_values = [point[0] for point in selected_points]
    y_values = [point[1] for point in selected_points]
    z_values = [point[2] for point in selected_points]
    crown_y = float(selection["crown_y_m"])
    back_z_max = float(selection["back_side_z_max_m"])
    selected_crown = sum(point[1] >= crown_y for point in selected_points)
    selected_back_side = sum(point[2] <= back_z_max for point in selected_points)

    evidence: dict[str, object] = {
        "schema": SCHEMA,
        "guide_count": guide_count,
        "segments": segments,
        "length_m": length_m,
        "root_width_m": root_width_m,
        "tip_width_m": tip_width_m,
        "root_offset_m": root_offset_m,
        "root_selection": selection,
        "unique_root_count": len(set(rooted.root_indices)),
        "selected_crown_roots": selected_crown,
        "selected_back_side_roots": selected_back_side,
        "root_x_range_m": [min(x_values), max(x_values)],
        "root_y_range_m": [min(y_values), max(y_values)],
        "root_z_range_m": [min(z_values), max(z_values)],
        "root_z_span_m": max(z_values) - min(z_values),
        "hair_validation": validation,
        "uv_validation": uv_report,
        "truth": {
            "source_grounded": True,
            "root_basis": "canonical hm08 head vertices + pinned eye plane",
            "preferred_scalp_hair_claim": False,
            "notes": [
                "v0.1 is a deterministic short-card groom, not a final hairstyle or fiber simulation.",
                "Crown plus behind-eye back/side selection avoids using the face as a generic sphere scalp.",
                "Hairline shape, temple transitions, card coverage and alpha sorting require real Godot visual judgment."
            ],
        },
    }
    return rooted, cards, uvmap, evidence


def build_preferred_hm08_short_scalp_hair():
    raw_head, _ = read_obj_uv(SEED_ROOT / "head.obj", name="hm08_head_v0_2")
    library = {
        name: load_target(SEED_ROOT / "targets" / f"{name}.target", license="CC0-source-remap")
        for name in sorted(DEFAULT_WEIGHTS)
    }
    identity, _ = mix_targets(raw_head, library, DEFAULT_WEIGHTS, name="sentinel_identity_for_scalp_hair")
    head_m = scale(identity, RAW_TO_M, name="sentinel_identity_scalp_hair_meters")
    eye_metadata = json.loads((SEED_ROOT / "eye-landmarks.json").read_text(encoding="utf-8"))
    return generate_hm08_short_scalp_hair(head_m, eye_metadata=eye_metadata)


if __name__ == "__main__":
    _, _, _, evidence = build_preferred_hm08_short_scalp_hair()
    print(json.dumps(evidence, indent=2, sort_keys=True))
