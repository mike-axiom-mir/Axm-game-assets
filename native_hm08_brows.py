#!/usr/bin/env python3
"""Source-grounded eyebrow card generation for the repaired hm08 face.

Brow anchors are derived from the current identity mesh and pinned eye centers.
Requested brow X/Y positions are sampled continuously on the real front-facing
triangle surface (barycentric interpolation), then offset slightly along the
interpolated local normal. This avoids quantizing a groom to source-vertex
spacing. No painted brow mask, face scan, or external grooming runtime is used.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from math import sqrt
from pathlib import Path

from native_geometry import Mesh, Vec3, scale, triangulate, vertex_normals
from native_hair import HairGuide, HairSystem, hair_cards_with_uv, validate_hair
from native_hm08_face_proof import DEFAULT_WEIGHTS
from native_hm08_landmarks import derive_hm08_face_landmarks
from native_targets import load_target, mix_targets
from native_uv import UVMap, read_obj_uv, validate_uv

SEED_ROOT = Path("seed_data/hm08_head_v0.2")
RAW_TO_M = 0.1
SCHEMA = "axm.game-assets.hm08-brows.v0.3"


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
    return _normalize(_add(_mul(tangent, 0.985), _mul(normal, 0.17)))


def _barycentric_xy(point_x: float, point_y: float, a: Vec3, b: Vec3, c: Vec3):
    x0, y0 = a[0], a[1]
    x1, y1 = b[0], b[1]
    x2, y2 = c[0], c[1]
    denominator = (y1-y2)*(x0-x2) + (x2-x1)*(y0-y2)
    if abs(denominator) <= 1e-14:
        return None
    w0 = ((y1-y2)*(point_x-x2) + (x2-x1)*(point_y-y2)) / denominator
    w1 = ((y2-y0)*(point_x-x2) + (x0-x2)*(point_y-y2)) / denominator
    w2 = 1.0 - w0 - w1
    if min(w0, w1, w2) < -1e-7:
        return None
    return w0, w1, w2


def sample_front_surface(
    mesh: Mesh,
    normals: list[Vec3],
    target_x: float,
    target_y: float,
    *,
    minimum_z: float,
) -> tuple[Vec3, Vec3, int, str]:
    """Sample the front-most projected mesh surface at an authored X/Y point.

    This is intentionally public because brows, lashes and later facial cards
    need one shared continuous surface truth instead of each re-inventing a
    nearest-vertex approximation.
    """
    tri = triangulate(mesh)
    candidates = []
    for face_index, face in enumerate(tri.faces):
        a, b, c = (tri.vertices[index] for index in face)
        bary = _barycentric_xy(target_x, target_y, a, b, c)
        if bary is None:
            continue
        w0, w1, w2 = bary
        z = a[2]*w0 + b[2]*w1 + c[2]*w2
        if z < minimum_z:
            continue
        normal = _normalize(tuple(
            normals[face[0]][axis]*w0 + normals[face[1]][axis]*w1 + normals[face[2]][axis]*w2
            for axis in range(3)
        ))
        if normal[2] <= 0.10:
            continue
        candidates.append((z, face_index, (target_x, target_y, z), normal))
    if candidates:
        _, face_index, surface, normal = max(candidates, key=lambda item: item[0])
        return surface, normal, face_index, "barycentric_front_triangle"

    fallback = [
        index for index, (point, normal) in enumerate(zip(mesh.vertices, normals))
        if point[2] >= minimum_z and normal[2] > 0.10
    ]
    if not fallback:
        raise ValueError("no front-facing hm08 surface available for facial anchor")
    vertex = min(
        fallback,
        key=lambda index: (
            (mesh.vertices[index][0]-target_x)**2 + (mesh.vertices[index][1]-target_y)**2,
            -mesh.vertices[index][2],
        ),
    )
    return mesh.vertices[vertex], _normalize(normals[vertex]), vertex, "nearest_vertex_fallback"


def generate_hm08_brows(
    head_m: Mesh,
    *,
    landmarks_raw,
    eye_metadata: dict[str, object],
    guides_per_brow: int = 24,
    guide_length_m: float = 0.0050,
    root_width_m: float = 0.00180,
    tip_width_m: float = 0.00038,
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
    anchor_surfaces: list[Vec3] = []
    sampling_methods: list[str] = []
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
            arch = 1.0 - (u * 0.82) ** 2
            target_y = eye_y_m + eye_to_nose_m * (0.29 + 0.095 * arch + 0.025 * sign * u)
            surface, normal, anchor_index, sampling_method = sample_front_surface(
                head_m,
                normals,
                target_x,
                target_y,
                minimum_z=minimum_z,
            )
            root = _add(surface, _mul(normal, root_offset_m))

            outward_amount = 0.18 + 0.66 * t
            desired = _normalize((sign * outward_amount, 0.96 - 0.28 * t, 0.0))
            direction = _tangent_direction(desired, normal)
            mid = _add(root, _mul(direction, guide_length_m * 0.52))
            tip_direction = _tangent_direction((sign * (outward_amount + 0.10), 0.66 - 0.22*t, 0.0), normal)
            tip = _add(mid, _mul(tip_direction, guide_length_m * 0.48))

            guides.append(HairGuide(
                points=[root, mid, tip],
                root_normal=normal,
                root_width=root_width_m,
                tip_width=tip_width_m,
                group=f"brow_{side}",
            ))
            anchor_indices.append(anchor_index)
            anchor_distances.append(_length(_sub(root, surface)))
            anchor_surfaces.append(surface)
            sampling_methods.append(sampling_method)
            per_side_anchor_x[side].append(surface[0])

    system = HairSystem(guides=guides, seed=seed, style="hm08_brows_v0.3_density_route")
    validation = validate_hair(system)
    if validation["status"] != "pass":
        raise ValueError(f"hm08 brow guide validation failed: {validation}")
    cards, uvmap = hair_cards_with_uv(system, name="sentinel_hm08_brows")
    uv_report = validate_uv(cards, uvmap)
    if uv_report["status"] != "pass":
        raise ValueError(f"hm08 brow card UV failed: {uv_report}")

    unique_surface_points = len({tuple(round(value, 8) for value in point) for point in anchor_surfaces})
    method_counts = {method: sampling_methods.count(method) for method in sorted(set(sampling_methods))}
    evidence = {
        "schema": SCHEMA,
        "guides_per_brow": guides_per_brow,
        "guide_count": len(guides),
        "guide_length_m": guide_length_m,
        "root_width_m": root_width_m,
        "tip_width_m": tip_width_m,
        "root_offset_m": root_offset_m,
        "anchor_count": len(anchor_indices),
        "unique_anchor_count": unique_surface_points,
        "unique_anchor_face_count": len(set(anchor_indices)),
        "surface_sampling": method_counts,
        "max_root_surface_distance_m": max(anchor_distances, default=0.0),
        "mean_root_surface_distance_m": sum(anchor_distances)/len(anchor_distances) if anchor_distances else 0.0,
        "left_anchor_x_range": [min(per_side_anchor_x["left"]), max(per_side_anchor_x["left"])],
        "right_anchor_x_range": [min(per_side_anchor_x["right"]), max(per_side_anchor_x["right"])],
        "hair_validation": validation,
        "uv_validation": uv_report,
        "truth": {
            "source_grounded": True,
            "placement_basis": "continuous current identity front surface + pinned hm08 eye landmarks",
            "preferred_geometry_route": True,
            "high_end_brow_claim": False,
            "notes": [
                "48-guide continuous-surface placement plus overlapping card widths is the current preferred brow geometry route after real Godot v0.3 evidence produced a readable eyebrow mass.",
                "The dedicated brow-density material remains a separate organ; geometry preference does not imply final groom quality.",
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
