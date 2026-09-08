#!/usr/bin/env python3
"""Source-grounded eyebrow card generation for the repaired hm08 face.

Brow anchors are derived from the current identity mesh and pinned eye centers.
Each short guide is snapped to a real front-face surface vertex, offset slightly
along the local normal, then grown along the local tangent plane. No painted
brow mask, face scan, or external grooming runtime is required.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from math import sqrt
from pathlib import Path

from native_geometry import Mesh, Vec3, scale, vertex_normals
from native_hair import HairGuide, HairSystem, hair_cards_with_uv, validate_hair
from native_hm08_face_proof import DEFAULT_WEIGHTS
from native_hm08_landmarks import derive_hm08_face_landmarks
from native_targets import load_target, mix_targets
from native_uv import UVMap, read_obj_uv, validate_uv

SEED_ROOT = Path("seed_data/hm08_head_v0.2")
RAW_TO_M = 0.1
SCHEMA = "axm.game-assets.hm08-brows.v0.1"


@dataclass(slots=True)
class BrowAssembly:
    system: HairSystem
    cards: Mesh
    uvmap: UVMap
    anchor_indices: list[int]
    anchor_surface_distances_m: list[float]
    evidence: dict[str, object]


def _dot(a: Vec3, b: Vec3) -> float:
    return a[0]*b[0] + a[1]*b[1] + a[2]*b[2]


def _add(a: Vec3, b: Vec3) -> Vec3:
    return a[0]+b[0], a[1]+b[1], a[2]+b[2]


def _sub(a: Vec3, b: Vec3) -> Vec3:
    return a[0]-b[0], a[1]-b[1], a[2]-b[2]


def _mul(v: Vec3, scalar: float) -> Vec3:
    return v[0]*scalar, v[1]*scalar, v[2]*scalar


def _length(v: Vec3) -> float:
    return sqrt(_dot(v, v))


def _normalize(v: Vec3) -> Vec3:
    length = _length(v)
    if length <= 1e-12:
        return 0.0, 1.0, 0.0
    return v[0]/length, v[1]/length, v[2]/length


def _tangent_direction(desired: Vec3, normal: Vec3) -> Vec3:
    normal = _normalize(normal)
    projected = _sub(desired, _mul(normal, _dot(desired, normal)))
    if _length(projected) <= 1e-10:
        projected = (1.0, 0.0, 0.0)
        projected = _sub(projected, _mul(normal, _dot(projected, normal)))
    tangent = _normalize(projected)
    # Tiny normal component keeps the free end above the skin instead of
    # allowing a tangent-plane numerical wobble to enter the forehead.
    return _normalize(_add(_mul(tangent, 0.985), _mul(normal, 0.17)))


def _nearest_front_surface_vertex(
    mesh: Mesh,
    normals: list[Vec3],
    target_x: float,
    target_y: float,
    *,
    minimum_z: float,
) -> int:
    candidates = [
        index for index, (point, normal) in enumerate(zip(mesh.vertices, normals))
        if point[2] >= minimum_z and normal[2] > 0.10
    ]
    if not candidates:
        raise ValueError("no front-facing hm08 surface vertices available for brow anchor")
    return min(
        candidates,
        key=lambda index: (
            (mesh.vertices[index][0]-target_x)**2 + (mesh.vertices[index][1]-target_y)**2,
            -mesh.vertices[index][2],
        ),
    )


def generate_hm08_brows(
    head_m: Mesh,
    *,
    landmarks_raw,
    eye_metadata: dict[str, object],
    guides_per_brow: int = 16,
    guide_length_m: float = 0.0052,
    root_width_m: float = 0.00125,
    tip_width_m: float = 0.00022,
    root_offset_m: float = 0.00055,
    seed: int = 52081,
) -> BrowAssembly:
    if guides_per_brow < 6:
        raise ValueError("hm08 brow needs at least six guides per brow")
    if guide_length_m <= 0.0 or root_width_m <= 0.0 or tip_width_m < 0.0:
        raise ValueError("invalid brow guide dimensions")

    normals = vertex_normals(head_m)
    eye_y_m = ((landmarks_raw.left_eye[1] + landmarks_raw.right_eye[1]) * 0.5) * RAW_TO_M
    eye_to_nose_m = (((landmarks_raw.left_eye[1] + landmarks_raw.right_eye[1]) * 0.5) - landmarks_raw.nose_tip[1]) * RAW_TO_M
    eye_half_sep_m = abs(landmarks_raw.left_eye[0] - landmarks_raw.right_eye[0]) * 0.5 * RAW_TO_M
    eye_z_m = ((landmarks_raw.left_eye[2] + landmarks_raw.right_eye[2]) * 0.5) * RAW_TO_M
    radius_m = float(eye_metadata["prototype_eye_radius_m"])
    minimum_z = eye_z_m + radius_m * 0.20

    guides: list[HairGuide] = []
    anchor_indices: list[int] = []
    anchor_distances: list[float] = []
    per_side_rows: dict[str, list[int]] = {"left": [], "right": []}
    per_side_anchor_x: dict[str, list[float]] = {"left": [], "right": []}

    for side, sign, eye in (
        ("left", 1.0, landmarks_raw.left_eye),
        ("right", -1.0, landmarks_raw.right_eye),
    ):
        eye_x_m = eye[0] * RAW_TO_M
        for guide_index in range(guides_per_brow):
            t = guide_index / (guides_per_brow - 1)
            u = t * 2.0 - 1.0
            target_x = eye_x_m + u * eye_half_sep_m * 0.78
            # Soft arch: center/outer brow sits slightly higher than inner.
            arch = 1.0 - (u * 0.82) ** 2
            target_y = eye_y_m + eye_to_nose_m * (0.29 + 0.095 * arch + 0.025 * sign * u)
            anchor = _nearest_front_surface_vertex(
                head_m,
                normals,
                target_x,
                target_y,
                minimum_z=minimum_z,
            )
            surface = head_m.vertices[anchor]
            normal = _normalize(normals[anchor])
            root = _add(surface, _mul(normal, root_offset_m))

            # Inner hairs stand more vertically; outer hairs increasingly flow
            # laterally toward the temple. Mirror the rule between sides.
            outward_amount = 0.18 + 0.66 * t
            desired = _normalize((sign * outward_amount, 0.96 - 0.28 * t, 0.0))
            direction = _tangent_direction(desired, normal)
            mid = _add(root, _mul(direction, guide_length_m * 0.52))
            # Slightly taper the tip back toward the face tangent while keeping
            # a tiny outward normal offset.
            tip_direction = _tangent_direction((sign * (outward_amount + 0.10), 0.66 - 0.22*t, 0.0), normal)
            tip = _add(mid, _mul(tip_direction, guide_length_m * 0.48))

            guides.append(HairGuide(
                points=[root, mid, tip],
                root_normal=normal,
                root_width=root_width_m,
                tip_width=tip_width_m,
                group=f"brow_{side}",
            ))
            anchor_indices.append(anchor)
            anchor_distances.append(_length(_sub(root, surface)))
            per_side_rows[side].append(anchor)
            per_side_anchor_x[side].append(surface[0])

    system = HairSystem(guides=guides, seed=seed, style="hm08_brows_v0.1")
    validation = validate_hair(system)
    if validation["status"] != "pass":
        raise ValueError(f"hm08 brow guide validation failed: {validation}")
    cards, uvmap = hair_cards_with_uv(system, name="sentinel_hm08_brows")
    uv_report = validate_uv(cards, uvmap)
    if uv_report["status"] != "pass":
        raise ValueError(f"hm08 brow card UV failed: {uv_report}")

    evidence = {
        "schema": SCHEMA,
        "guides_per_brow": guides_per_brow,
        "guide_count": len(guides),
        "guide_length_m": guide_length_m,
        "root_width_m": root_width_m,
        "tip_width_m": tip_width_m,
        "root_offset_m": root_offset_m,
        "anchor_count": len(anchor_indices),
        "unique_anchor_count": len(set(anchor_indices)),
        "max_root_surface_distance_m": max(anchor_distances, default=0.0),
        "mean_root_surface_distance_m": sum(anchor_distances)/len(anchor_distances) if anchor_distances else 0.0,
        "left_anchor_x_range": [min(per_side_anchor_x["left"]), max(per_side_anchor_x["left"])],
        "right_anchor_x_range": [min(per_side_anchor_x["right"]), max(per_side_anchor_x["right"])],
        "hair_validation": validation,
        "uv_validation": uv_report,
        "truth": {
            "source_grounded": True,
            "placement_basis": "current identity mesh surface + pinned hm08 eye landmarks",
            "aesthetic_brow_claim": False,
            "notes": [
                "Brow roots are real head-surface anchors, not painted texture coordinates.",
                "Card groom is an authored first pass; density/shape still requires real engine visual judgment."
            ],
        },
    }
    return BrowAssembly(system, cards, uvmap, anchor_indices, anchor_distances, evidence)


def build_preferred_hm08_brows() -> BrowAssembly:
    raw_head, _ = read_obj_uv(SEED_ROOT / "head.obj", name="hm08_head_v0_2")
    library = {
        name: load_target(SEED_ROOT / "targets" / f"{name}.target", license="CC0-source-remap")
        for name in sorted(DEFAULT_WEIGHTS)
    }
    identity, _ = mix_targets(raw_head, library, DEFAULT_WEIGHTS, name="sentinel_identity_for_brows")
    eye_metadata = json.loads((SEED_ROOT / "eye-landmarks.json").read_text(encoding="utf-8"))
    landmarks = derive_hm08_face_landmarks(identity, eye_metadata)
    return generate_hm08_brows(scale(identity, RAW_TO_M, name="sentinel_identity_brow_meters"), landmarks_raw=landmarks, eye_metadata=eye_metadata)


if __name__ == "__main__":
    assembly = build_preferred_hm08_brows()
    print(json.dumps(assembly.evidence, indent=2, sort_keys=True))
