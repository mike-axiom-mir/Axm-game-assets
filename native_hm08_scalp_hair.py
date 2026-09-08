#!/usr/bin/env python3
"""hm08 short laid-scalp-hair root selection and card state v0.2.

v0.1 proved that 256 unique canonical roots can import/render, but its broad
behind-eye mask leaked onto temples/ears and random guide flow produced sparse
scratches and neck tails. v0.2 keeps a much tighter cranial field, explicitly
balances crown/side/back roots, and lays short cards along deterministic scalp
flow instead of random free-space spikes.
"""
from __future__ import annotations

import json
import random
from math import sqrt
from pathlib import Path

from native_geometry import Mesh, Vec3, bounds, scale, vertex_normals
from native_hair import HairGuide, HairSystem, hair_cards_with_uv, validate_hair
from native_hair_roots import select_root_indices
from native_hm08_face_proof import DEFAULT_WEIGHTS
from native_targets import load_target, mix_targets
from native_uv import UVMap, read_obj_uv, validate_uv

SEED_ROOT = Path("seed_data/hm08_head_v0.2")
RAW_TO_M = 0.1
SCHEMA = "axm.game-assets.hm08-short-scalp-hair.v0.2"


def _add(a: Vec3, b: Vec3) -> Vec3:
    return a[0] + b[0], a[1] + b[1], a[2] + b[2]


def _sub(a: Vec3, b: Vec3) -> Vec3:
    return a[0] - b[0], a[1] - b[1], a[2] - b[2]


def _mul(v: Vec3, scalar: float) -> Vec3:
    return v[0] * scalar, v[1] * scalar, v[2] * scalar


def _dot(a: Vec3, b: Vec3) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _length(v: Vec3) -> float:
    return sqrt(_dot(v, v))


def _normalize(v: Vec3) -> Vec3:
    length = _length(v)
    if length <= 1e-12:
        return 0.0, -1.0, 0.0
    return v[0] / length, v[1] / length, v[2] / length


def _laid_direction(desired: Vec3, normal: Vec3, *, outward: float = 0.16) -> Vec3:
    normal = _normalize(normal)
    desired = _normalize(desired)
    tangent = _sub(desired, _mul(normal, _dot(desired, normal)))
    if _length(tangent) <= 1e-10:
        tangent = (0.0, -1.0, -0.2)
        tangent = _sub(tangent, _mul(normal, _dot(tangent, normal)))
    tangent = _normalize(tangent)
    return _normalize(_add(_mul(tangent, 1.0 - outward), _mul(normal, outward)))


def select_hm08_scalp_candidates(
    head_m: Mesh,
    eye_metadata: dict[str, object],
) -> tuple[dict[str, list[int]], dict[str, float | int]]:
    lo, hi = bounds(head_m)
    eye_y = sum(float(eye_metadata["eyes"][side]["center_m"][1]) for side in ("left", "right")) * 0.5
    eye_z = sum(float(eye_metadata["eyes"][side]["center_m"][2]) for side in ("left", "right")) * 0.5
    half_width = max(abs(lo[0]), abs(hi[0]), 1e-9)

    # Keep the already-repaired forehead/temple mask fixed. The previous
    # 271-root failure came from an overly narrow posterior field, so expand
    # only the back-of-skull region. It stays behind the eye plane and below
    # the crown, avoiding the v0.1 ear/forehead leak while preserving the
    # 320-unique-root density target.
    crown_y = eye_y + 0.042
    side_y = eye_y + 0.010
    back_y = eye_y - 0.018
    side_z_max = eye_z - 0.004
    back_z_max = eye_z - 0.028
    crown_lateral_limit = half_width * 0.89
    side_lateral_limit = half_width * 0.74
    back_lateral_limit = half_width * 0.84

    crown: list[int] = []
    side: list[int] = []
    back: list[int] = []
    for index, point in enumerate(head_m.vertices):
        x, y, z = point
        if y >= crown_y and abs(x) <= crown_lateral_limit:
            crown.append(index)
            continue
        if y >= side_y and z <= side_z_max and abs(x) <= side_lateral_limit:
            side.append(index)
            continue
        if y >= back_y and z <= back_z_max and abs(x) <= back_lateral_limit:
            back.append(index)

    evidence = {
        "candidate_count": len(set(crown) | set(side) | set(back)),
        "crown_candidates": len(crown),
        "side_candidates": len(side),
        "back_candidates": len(back),
        "crown_y_m": crown_y,
        "side_y_m": side_y,
        "back_y_m": back_y,
        "side_z_max_m": side_z_max,
        "back_z_max_m": back_z_max,
        "crown_lateral_limit_m": crown_lateral_limit,
        "side_lateral_limit_m": side_lateral_limit,
        "back_lateral_limit_m": back_lateral_limit,
    }
    return {"crown": crown, "side": side, "back": back}, evidence


def _balanced_roots(
    regions: dict[str, list[int]],
    *,
    guide_count: int,
    seed: int,
) -> tuple[list[int], dict[str, int]]:
    quotas = {
        "crown": round(guide_count * 0.45),
        "side": round(guide_count * 0.35),
    }
    quotas["back"] = guide_count - quotas["crown"] - quotas["side"]
    used: set[int] = set()
    selected: list[int] = []
    selected_counts = {"crown": 0, "side": 0, "back": 0, "fill": 0}

    for offset, region in enumerate(("crown", "side", "back")):
        available = sorted(set(regions[region]) - used)
        take = min(quotas[region], len(available))
        if take:
            rows = select_root_indices(available, guide_count=take, seed=seed + 101 * (offset + 1))
            selected.extend(rows)
            used.update(rows)
            selected_counts[region] = len(rows)

    if len(selected) < guide_count:
        union = sorted((set(regions["crown"]) | set(regions["side"]) | set(regions["back"])) - used)
        need = guide_count - len(selected)
        if len(union) < need:
            raise ValueError(f"hm08 v0.2 scalp mask has only {len(selected)+len(union)} unique roots for {guide_count} guides")
        fill = select_root_indices(union, guide_count=need, seed=seed + 909)
        selected.extend(fill)
        used.update(fill)
        selected_counts["fill"] = len(fill)

    if len(selected) != guide_count or len(set(selected)) != guide_count:
        raise ValueError("balanced hm08 scalp selection did not produce unique requested roots")
    return selected, selected_counts


def _flow_class(point: Vec3, *, crown_y: float, side_y: float, back_z_max: float) -> str:
    _x, y, z = point
    if y >= crown_y:
        return "crown_front" if z > 0.105 else "crown_back"
    if z <= back_z_max:
        return "back"
    if y >= side_y:
        return "side"
    return "back"


def _desired_flow(point: Vec3, flow_class: str, rng: random.Random) -> Vec3:
    x, _y, _z = point
    sign = 1.0 if x >= 0.0 else -1.0
    jitter_x = rng.uniform(-0.035, 0.035)
    jitter_y = rng.uniform(-0.035, 0.035)
    jitter_z = rng.uniform(-0.035, 0.035)
    if flow_class == "crown_front":
        base = (sign * 0.06, -0.18, -1.00)
    elif flow_class == "crown_back":
        base = (sign * 0.10, -0.40, -0.88)
    elif flow_class == "side":
        base = (sign * 0.16, -0.82, -0.50)
    else:
        base = (sign * 0.08, -1.00, -0.24)
    return _normalize((base[0] + jitter_x, base[1] + jitter_y, base[2] + jitter_z))


def generate_hm08_short_scalp_hair(
    head_m: Mesh,
    *,
    eye_metadata: dict[str, object],
    guide_count: int = 320,
    segments: int = 5,
    length_m: float = 0.020,
    root_width_m: float = 0.0065,
    tip_width_m: float = 0.0012,
    root_offset_m: float = 0.00045,
    seed: int = 72081,
) -> tuple[list[int], Mesh, UVMap, dict[str, object]]:
    regions, selection = select_hm08_scalp_candidates(head_m, eye_metadata)
    root_indices, selected_counts = _balanced_roots(regions, guide_count=guide_count, seed=seed)
    normals = vertex_normals(head_m)
    rng = random.Random(seed ^ 0x51A1)
    guides: list[HairGuide] = []
    flow_counts: dict[str, int] = {"crown_front": 0, "crown_back": 0, "side": 0, "back": 0}
    first_outward_dots: list[float] = []

    crown_y = float(selection["crown_y_m"])
    side_y = float(selection["side_y_m"])
    back_z_max = float(selection["back_z_max_m"])
    step = length_m / (segments - 1)
    for vertex_index in root_indices:
        surface = head_m.vertices[vertex_index]
        normal = _normalize(normals[vertex_index])
        root = _add(surface, _mul(normal, root_offset_m))
        flow_class = _flow_class(surface, crown_y=crown_y, side_y=side_y, back_z_max=back_z_max)
        flow_counts[flow_class] += 1
        desired = _desired_flow(surface, flow_class, rng)
        direction = _laid_direction(desired, normal, outward=0.17)
        first_outward_dots.append(_dot(direction, normal))
        points = [root]
        position = root
        for segment in range(1, segments):
            t = segment / (segments - 1)
            bend = _normalize((desired[0] * (1.0 - 0.08 * t), desired[1] - 0.10 * t, desired[2] - 0.04 * t))
            direction = _laid_direction(bend, normal, outward=0.13 if segment > 1 else 0.17)
            position = _add(position, _mul(direction, step))
            points.append(position)
        guides.append(HairGuide(points, normal, root_width_m, tip_width_m, group=f"scalp_{flow_class}"))

    system = HairSystem(guides, seed, "hm08_short_scalp_laid_v0.2")
    validation = validate_hair(system)
    if validation["status"] != "pass":
        raise ValueError(f"hm08 v0.2 scalp hair guide validation failed: {validation}")
    cards, uvmap = hair_cards_with_uv(system, name="sentinel_hm08_short_scalp_hair_v0_2")
    uv_report = validate_uv(cards, uvmap)
    if uv_report["status"] != "pass":
        raise ValueError(f"hm08 v0.2 scalp hair UV failed: {uv_report}")

    selected_points = [head_m.vertices[index] for index in root_indices]
    x_values = [point[0] for point in selected_points]
    y_values = [point[1] for point in selected_points]
    z_values = [point[2] for point in selected_points]
    evidence: dict[str, object] = {
        "schema": SCHEMA,
        "guide_count": guide_count,
        "segments": segments,
        "length_m": length_m,
        "root_width_m": root_width_m,
        "tip_width_m": tip_width_m,
        "root_offset_m": root_offset_m,
        "root_selection": selection,
        "selected_region_counts": selected_counts,
        "flow_counts": flow_counts,
        "unique_root_count": len(set(root_indices)),
        "root_x_range_m": [min(x_values), max(x_values)],
        "root_y_range_m": [min(y_values), max(y_values)],
        "root_z_range_m": [min(z_values), max(z_values)],
        "root_z_span_m": max(z_values) - min(z_values),
        "mean_first_outward_dot": sum(first_outward_dots) / len(first_outward_dots),
        "min_first_outward_dot": min(first_outward_dots),
        "hair_validation": validation,
        "uv_validation": uv_report,
        "truth": {
            "source_grounded": True,
            "root_basis": "tightened canonical hm08 cranial cap + pinned eye plane",
            "v0_1_visual_repair": "tighten_temples_and_lay_guides_along_scalp_flow",
            "native_gate_repair": "posterior-only scalp expansion preserves the 320-root target without reopening the rejected forehead/ear mask",
            "preferred_scalp_hair_claim": False,
            "notes": [
                "v0.1 rendered as sparse masked scratches with temple/ear leakage and random tails; v0.2 narrows roots and replaces random free flow with crown/side/back scalp directions.",
                "The current repair expands only the posterior scalp field after CI proved the earlier v0.2 mask had 271 safe unique roots for a 320-root target.",
                "Hairline, coverage and final groom quality remain real Godot visual gates."
            ],
        },
    }
    return root_indices, cards, uvmap, evidence


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
