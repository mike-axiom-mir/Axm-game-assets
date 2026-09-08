#!/usr/bin/env python3
"""Source-grounded upper-eyelash micro-ribbons for the repaired hm08 face.

v0.2 keeps the continuous hm08 eyelid-surface root mechanism from v0.1 but
moves the authored lash line closer to the eye and redirects growth forward
rather than mostly upward after real Godot evidence showed a floating dotted
fringe. Lower lashes remain a separate later gate.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path

from native_geometry import Mesh, Vec3, scale, vertex_normals
from native_hair import HairGuide, HairSystem, hair_cards_with_uv, validate_hair
from native_hm08_brows import sample_front_surface
from native_hm08_face_proof import DEFAULT_WEIGHTS
from native_hm08_landmarks import derive_hm08_face_landmarks
from native_targets import load_target, mix_targets
from native_uv import UVMap, read_obj_uv, validate_uv

SEED_ROOT = Path("seed_data/hm08_head_v0.2")
RAW_TO_M = 0.1
SCHEMA = "axm.game-assets.hm08-upper-lashes.v0.2"


@dataclass(slots=True)
class LashAssembly:
    system: HairSystem
    cards: Mesh
    uvmap: UVMap
    evidence: dict[str, object]


def _add(a: Vec3, b: Vec3) -> Vec3:
    return a[0] + b[0], a[1] + b[1], a[2] + b[2]


def _sub(a: Vec3, b: Vec3) -> Vec3:
    return a[0] - b[0], a[1] - b[1], a[2] - b[2]


def _mul(v: Vec3, scalar: float) -> Vec3:
    return v[0] * scalar, v[1] * scalar, v[2] * scalar


def _dot(a: Vec3, b: Vec3) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _length(v: Vec3) -> float:
    return math.sqrt(_dot(v, v))


def _normalize(v: Vec3) -> Vec3:
    length = _length(v)
    if length <= 1e-12:
        return 0.0, 1.0, 0.0
    return v[0] / length, v[1] / length, v[2] / length


def generate_hm08_upper_lashes(
    head_m: Mesh,
    *,
    landmarks_raw,
    eye_metadata: dict[str, object],
    guides_per_eye: int = 24,
    guide_length_m: float = 0.0065,
    root_width_m: float = 0.00050,
    tip_width_m: float = 0.000055,
    root_offset_m: float = 0.00022,
    seed: int = 62081,
) -> LashAssembly:
    if guides_per_eye < 8:
        raise ValueError("upper lashes need at least eight guides per eye")
    if guide_length_m <= 0.0 or root_width_m <= 0.0 or tip_width_m < 0.0 or tip_width_m >= root_width_m:
        raise ValueError("invalid upper-lash dimensions")

    normals = vertex_normals(head_m)
    radius_m = float(eye_metadata["prototype_eye_radius_m"])
    guides: list[HairGuide] = []
    surface_methods: list[str] = []
    root_surface_distances: list[float] = []
    root_eye_ratios: list[float] = []
    per_side_x: dict[str, list[float]] = {"left": [], "right": []}

    for side, sign, eye_key in (("left", 1.0, "left"), ("right", -1.0, "right")):
        center = tuple(float(value) for value in eye_metadata["eyes"][eye_key]["center_m"])
        eye_x, eye_y, eye_z = center
        for guide_index in range(guides_per_eye):
            t = guide_index / (guides_per_eye - 1)
            u = t * 2.0 - 1.0
            arch = math.sqrt(max(0.0, 1.0 - u * u))
            target_x = eye_x + sign * u * radius_m * 0.78
            # v0.1 used 0.14 + 0.22*arch and read too high in Godot. Lower the
            # authored line while preserving the same eye-centered curve.
            target_y = eye_y + radius_m * (0.08 + 0.18 * arch)
            surface, normal, _anchor, method = sample_front_surface(
                head_m,
                normals,
                target_x,
                target_y,
                minimum_z=eye_z + radius_m * 0.38,
            )
            root = _add(surface, _mul(normal, root_offset_m))

            # v0.2 grows primarily along the eyelid's outward/front normal,
            # with only a modest upward curl. This should read in profile rather
            # than standing vertically above the lid like v0.1.
            lateral = sign * (0.04 + 0.14 * t)
            first_direction = _normalize(_add(_mul(normal, 0.88), (lateral, 0.26 + arch * 0.05, 0.0)))
            local_length = guide_length_m * (0.91 + 0.09 * arch + 0.05 * t)
            mid = _add(root, _mul(first_direction, local_length * 0.55))
            tip_direction = _normalize(_add(_mul(normal, 0.70), (sign * (0.08 + 0.18 * t), 0.40 + arch * 0.04, 0.0)))
            tip = _add(mid, _mul(tip_direction, local_length * 0.45))

            guides.append(HairGuide(
                points=[root, mid, tip],
                root_normal=normal,
                root_width=root_width_m,
                tip_width=tip_width_m,
                group=f"upper_lash_{side}",
            ))
            surface_methods.append(method)
            root_surface_distances.append(_length(_sub(root, surface)))
            root_eye_ratios.append(_length(_sub(root, center)) / radius_m)
            per_side_x[side].append(surface[0])

    system = HairSystem(guides=guides, seed=seed, style="hm08_upper_lashes_v0.2_forward")
    validation = validate_hair(system)
    if validation["status"] != "pass":
        raise ValueError(f"upper-lash guide validation failed: {validation}")
    cards, uvmap = hair_cards_with_uv(system, name="sentinel_hm08_upper_lashes")
    uv_report = validate_uv(cards, uvmap)
    if uv_report["status"] != "pass":
        raise ValueError(f"upper-lash UV validation failed: {uv_report}")

    method_counts = {method: surface_methods.count(method) for method in sorted(set(surface_methods))}
    evidence = {
        "schema": SCHEMA,
        "guides_per_eye": guides_per_eye,
        "guide_count": len(guides),
        "guide_length_m": guide_length_m,
        "root_width_m": root_width_m,
        "tip_width_m": tip_width_m,
        "root_offset_m": root_offset_m,
        "surface_sampling": method_counts,
        "max_root_surface_distance_m": max(root_surface_distances, default=0.0),
        "mean_root_surface_distance_m": sum(root_surface_distances) / len(root_surface_distances) if root_surface_distances else 0.0,
        "min_root_eye_radius_ratio": min(root_eye_ratios, default=0.0),
        "max_root_eye_radius_ratio": max(root_eye_ratios, default=0.0),
        "left_root_x_range": [min(per_side_x["left"]), max(per_side_x["left"])],
        "right_root_x_range": [min(per_side_x["right"]), max(per_side_x["right"])],
        "hair_validation": validation,
        "uv_validation": uv_report,
        "truth": {
            "source_grounded": True,
            "placement_basis": "continuous upper-eyelid surface around pinned hm08 eye centers",
            "upper_lashes_only": True,
            "preferred_lash_claim": False,
            "v0_1_visual_repair": "lower_root_curve_and_forward_bias",
            "notes": [
                "v0.1 roots were structurally valid but read too high/vertical in Godot; v0.2 lowers the line and increases forward projection without changing the source-grounded eye anchors.",
                "Final eyelid contact and visual density still require real Godot close views.",
                "Lower lashes remain intentionally absent."
            ],
        },
    }
    return LashAssembly(system, cards, uvmap, evidence)


def build_preferred_hm08_upper_lashes() -> LashAssembly:
    raw_head, _ = read_obj_uv(SEED_ROOT / "head.obj", name="hm08_head_v0_2")
    library = {
        name: load_target(SEED_ROOT / "targets" / f"{name}.target", license="CC0-source-remap")
        for name in sorted(DEFAULT_WEIGHTS)
    }
    identity, _ = mix_targets(raw_head, library, DEFAULT_WEIGHTS, name="sentinel_identity_for_lashes")
    eye_metadata = json.loads((SEED_ROOT / "eye-landmarks.json").read_text(encoding="utf-8"))
    landmarks = derive_hm08_face_landmarks(identity, eye_metadata)
    head_m = scale(identity, RAW_TO_M, name="sentinel_identity_lash_meters")
    return generate_hm08_upper_lashes(head_m, landmarks_raw=landmarks, eye_metadata=eye_metadata)


if __name__ == "__main__":
    assembly = build_preferred_hm08_upper_lashes()
    print(json.dumps(assembly.evidence, indent=2, sort_keys=True))
