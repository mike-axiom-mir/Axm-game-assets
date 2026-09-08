#!/usr/bin/env python3
"""Native geometry-grounded facial landmarks for the repaired hm08 head.

The pinned hm08 seed provides topology and source-grounded eye centers. This
module derives additional authoring landmarks from that canonical geometry
without relying on crop boundaries, proprietary labels, face scans, or an
external runtime.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from statistics import median

from native_geometry import Mesh, Vec3, bounds
from native_uv import read_obj_uv

SEED_ROOT = Path("seed_data/hm08_head_v0.2")
SCHEMA = "axm.game-assets.hm08-face-landmarks.v0.1"


@dataclass(frozen=True, slots=True)
class Hm08FaceLandmarks:
    left_eye: Vec3
    right_eye: Vec3
    nose_tip: Vec3
    mouth_center: Vec3
    chin_center: Vec3
    bounds_min: Vec3
    bounds_max: Vec3
    evidence: dict[str, object]


def _weighted_mean(values: list[tuple[float, float]]) -> float:
    total = sum(weight for _, weight in values)
    if total <= 1e-12:
        raise ValueError("landmark weighted mean has zero weight")
    return sum(value * weight for value, weight in values) / total


def derive_hm08_face_landmarks(mesh: Mesh, eye_metadata: dict[str, object]) -> Hm08FaceLandmarks:
    if not mesh.vertices:
        raise ValueError("hm08 landmark derivation requires geometry")
    left_eye = tuple(float(v) for v in eye_metadata["eyes"]["left"]["center_raw"])
    right_eye = tuple(float(v) for v in eye_metadata["eyes"]["right"]["center_raw"])
    nose_tip = max(mesh.vertices, key=lambda vertex: vertex[2])
    lo, hi = bounds(mesh)

    eye_y = (left_eye[1] + right_eye[1]) * 0.5
    eye_half_sep = abs(left_eye[0] - right_eye[0]) * 0.5
    eye_to_nose = eye_y - nose_tip[1]
    if eye_to_nose <= 0.05:
        raise ValueError(f"unexpected hm08 eye/nose geometry: eye_to_nose={eye_to_nose}")

    # The mouth lies in the central forward face below the nose. Define the
    # search band from the face's own eye-to-nose scale, then use the most
    # forward vertices in that band as the lip-surface signal. This avoids
    # hard-coded source vertex ids while remaining fixed-topology friendly.
    mouth_band_lo = nose_tip[1] - eye_to_nose * 1.42
    mouth_band_hi = nose_tip[1] - eye_to_nose * 0.48
    central_half_width = max(eye_half_sep * 0.92, (hi[0] - lo[0]) * 0.12)
    face_front_floor = lo[2] + (hi[2] - lo[2]) * 0.60
    candidates = [
        vertex for vertex in mesh.vertices
        if abs(vertex[0]) <= central_half_width
        and mouth_band_lo <= vertex[1] <= mouth_band_hi
        and vertex[2] >= face_front_floor
    ]
    if len(candidates) < 12:
        raise ValueError(
            "too few mouth landmark candidates: "
            f"{len(candidates)} band=({mouth_band_lo},{mouth_band_hi}) width={central_half_width} front={face_front_floor}"
        )
    z_values = sorted(vertex[2] for vertex in candidates)
    forward_threshold = z_values[max(0, int(len(z_values) * 0.72) - 1)]
    forward = [vertex for vertex in candidates if vertex[2] >= forward_threshold]
    if len(forward) < 4:
        raise ValueError("mouth landmark forward candidate set unexpectedly small")
    z_max = max(vertex[2] for vertex in forward)
    z_span = max(hi[2] - lo[2], 1e-9)
    sigma = max(z_span * 0.035, 1e-4)
    weighted = []
    for x, y, z in forward:
        # Prefer forward surface but keep a broad enough distribution that a
        # single protruding vertex cannot become the mouth landmark.
        weight = math.exp((z - z_max) / sigma)
        weighted.append(((x, y, z), weight))
    mouth_center = (
        _weighted_mean([(point[0], weight) for point, weight in weighted]),
        _weighted_mean([(point[1], weight) for point, weight in weighted]),
        _weighted_mean([(point[2], weight) for point, weight in weighted]),
    )
    # Bilateral topology should keep the semantic mouth center almost exactly
    # on the midline. Normalize tiny asymmetric numerical drift only.
    if abs(mouth_center[0]) < central_half_width * 0.08:
        mouth_center = (0.0, mouth_center[1], mouth_center[2])

    # Chin is a separate lower-center surface landmark used later for jaw/lip
    # secondary forms. Again derive relative to the face scale, not source ids.
    chin_band_lo = max(lo[1], mouth_center[1] - eye_to_nose * 1.15)
    chin_band_hi = mouth_center[1] - eye_to_nose * 0.28
    chin_candidates = [
        vertex for vertex in mesh.vertices
        if abs(vertex[0]) <= central_half_width * 0.72
        and chin_band_lo <= vertex[1] <= chin_band_hi
        and vertex[2] >= lo[2] + (hi[2] - lo[2]) * 0.52
    ]
    if len(chin_candidates) < 6:
        raise ValueError(f"too few chin candidates: {len(chin_candidates)}")
    chin_front = sorted(chin_candidates, key=lambda vertex: vertex[2], reverse=True)[:max(6, len(chin_candidates) // 4)]
    chin_center = (
        median(vertex[0] for vertex in chin_front),
        median(vertex[1] for vertex in chin_front),
        median(vertex[2] for vertex in chin_front),
    )
    if abs(chin_center[0]) < central_half_width * 0.08:
        chin_center = (0.0, chin_center[1], chin_center[2])

    evidence = {
        "schema": SCHEMA,
        "method": "canonical_geometry_proportional_search",
        "coordinate_space": "raw_makehuman_hm08_obj",
        "eye_to_nose": eye_to_nose,
        "eye_half_separation": eye_half_sep,
        "mouth_search": {
            "y_band": [mouth_band_lo, mouth_band_hi],
            "central_half_width": central_half_width,
            "front_floor": face_front_floor,
            "candidate_count": len(candidates),
            "forward_candidate_count": len(forward),
            "forward_threshold": forward_threshold,
        },
        "chin_search": {
            "y_band": [chin_band_lo, chin_band_hi],
            "candidate_count": len(chin_candidates),
            "front_candidate_count": len(chin_front),
        },
        "truth": {
            "source_vertex_ids_required": False,
            "crop_boundary_used": False,
            "human_scan_used": False,
            "notes": [
                "Eye centers are pinned source metadata; mouth/chin are AXM-native proportional geometry inferences.",
                "These are authoring landmarks, not biometric measurements or identity recognition."
            ],
        },
    }
    return Hm08FaceLandmarks(
        left_eye=left_eye,  # type: ignore[arg-type]
        right_eye=right_eye,  # type: ignore[arg-type]
        nose_tip=nose_tip,
        mouth_center=mouth_center,
        chin_center=chin_center,
        bounds_min=lo,
        bounds_max=hi,
        evidence=evidence,
    )


def load_preferred_hm08_landmarks() -> Hm08FaceLandmarks:
    mesh, _ = read_obj_uv(SEED_ROOT / "head.obj", name="hm08_head_v0_2")
    eye_metadata = json.loads((SEED_ROOT / "eye-landmarks.json").read_text(encoding="utf-8"))
    return derive_hm08_face_landmarks(mesh, eye_metadata)


def landmark_packet(landmarks: Hm08FaceLandmarks) -> dict[str, object]:
    return {
        "schema": SCHEMA,
        "left_eye": list(landmarks.left_eye),
        "right_eye": list(landmarks.right_eye),
        "nose_tip": list(landmarks.nose_tip),
        "mouth_center": list(landmarks.mouth_center),
        "chin_center": list(landmarks.chin_center),
        "bounds": {"min": list(landmarks.bounds_min), "max": list(landmarks.bounds_max)},
        "evidence": landmarks.evidence,
    }


if __name__ == "__main__":
    print(json.dumps(landmark_packet(load_preferred_hm08_landmarks()), indent=2, sort_keys=True))
