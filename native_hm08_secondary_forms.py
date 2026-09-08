#!/usr/bin/env python3
"""AXM-native secondary facial form targets for repaired hm08 topology.

These targets are authored from canonical geometry and AXM facial landmarks.
They remain sparse/reversible source state and intentionally use low-millimeter
amplitudes. They are not a claim of anatomically final sculpt quality.
"""
from __future__ import annotations

import json
from pathlib import Path

from native_geometry import Mesh, Vec3
from native_hm08_landmarks import Hm08FaceLandmarks, derive_hm08_face_landmarks
from native_target_authoring import author_normal_target, gaussian_region
from native_targets import SparseTarget, mix_targets
from native_uv import read_obj_uv

SEED_ROOT = Path("seed_data/hm08_head_v0.2")
SCHEMA = "axm.game-assets.hm08-secondary-forms.v0.1"


def _front_eye_z(landmarks: Hm08FaceLandmarks, eye_metadata: dict[str, object]) -> float:
    return (landmarks.left_eye[2] + landmarks.right_eye[2]) * 0.5 + float(eye_metadata["prototype_eye_radius_raw"]) * 0.82


def build_secondary_form_targets(
    mesh: Mesh,
    landmarks: Hm08FaceLandmarks,
    eye_metadata: dict[str, object],
) -> dict[str, SparseTarget]:
    eye_y = (landmarks.left_eye[1] + landmarks.right_eye[1]) * 0.5
    eye_half_sep = abs(landmarks.left_eye[0] - landmarks.right_eye[0]) * 0.5
    eye_to_nose = eye_y - landmarks.nose_tip[1]
    nose_to_mouth = landmarks.nose_tip[1] - landmarks.mouth_center[1]
    eye_front_z = _front_eye_z(landmarks, eye_metadata)
    mouth = landmarks.mouth_center

    targets: dict[str, SparseTarget] = {}

    # Brow ridge: broad forward support above each eye, deliberately small.
    for side, eye in (("left", landmarks.left_eye), ("right", landmarks.right_eye)):
        targets[f"{side}_brow_ridge"] = author_normal_target(
            mesh,
            f"{side}_brow_ridge",
            0.012,
            region=gaussian_region(
                (eye[0], eye_y + eye_to_nose * 0.30, eye_front_z - 0.020),
                (eye_half_sep * 0.55, eye_to_nose * 0.32, 0.16),
            ),
            threshold=0.00025,
            source="AXM hm08 secondary-form authoring v0.1",
        )

        # Upper lid gains a subtle convex form; lower lid/tear trough gets a
        # tiny inward form immediately below the eye. These are geometry
        # targets only; blink/expression motion remains separate morph state.
        targets[f"{side}_upper_lid_form"] = author_normal_target(
            mesh,
            f"{side}_upper_lid_form",
            0.006,
            region=gaussian_region(
                (eye[0], eye_y + eye_to_nose * 0.035, eye_front_z),
                (eye_half_sep * 0.36, eye_to_nose * 0.14, 0.075),
            ),
            threshold=0.00020,
            source="AXM hm08 secondary-form authoring v0.1",
        )
        targets[f"{side}_lower_lid_trough"] = author_normal_target(
            mesh,
            f"{side}_lower_lid_trough",
            -0.004,
            region=gaussian_region(
                (eye[0], eye_y - eye_to_nose * 0.16, eye_front_z - 0.018),
                (eye_half_sep * 0.40, eye_to_nose * 0.18, 0.090),
            ),
            threshold=0.00016,
            source="AXM hm08 secondary-form authoring v0.1",
        )

    # Lip volume follows the derived mouth surface, not a crop boundary.
    targets["lip_volume"] = author_normal_target(
        mesh,
        "lip_volume",
        0.009,
        region=gaussian_region(
            mouth,
            (eye_half_sep * 0.72, max(nose_to_mouth * 0.15, 0.055), 0.10),
        ),
        threshold=0.00018,
        source="AXM hm08 secondary-form authoring v0.1",
    )

    # Philtrum and nasolabial creases are shallow inward forms. Their centers
    # are expressed relative to nose-to-mouth distance so the same mechanism
    # survives future identity target mixes.
    philtrum_center = (
        0.0,
        mouth[1] + nose_to_mouth * 0.34,
        mouth[2] + (landmarks.nose_tip[2] - mouth[2]) * 0.28,
    )
    targets["philtrum_groove"] = author_normal_target(
        mesh,
        "philtrum_groove",
        -0.0035,
        region=gaussian_region(
            philtrum_center,
            (eye_half_sep * 0.16, max(nose_to_mouth * 0.26, 0.070), 0.085),
        ),
        threshold=0.00014,
        source="AXM hm08 secondary-form authoring v0.1",
    )

    cheek_y = mouth[1] + (eye_y - mouth[1]) * 0.58
    cheek_x = max(eye_half_sep * 0.78, 0.21)
    cheek_z = mouth[2] + (eye_front_z - mouth[2]) * 0.42
    for side, sign in (("left", 1.0), ("right", -1.0)):
        targets[f"{side}_cheek_plane"] = author_normal_target(
            mesh,
            f"{side}_cheek_plane",
            0.006,
            region=gaussian_region(
                (sign * cheek_x, cheek_y, cheek_z),
                (eye_half_sep * 0.52, eye_to_nose * 0.52, 0.19),
            ),
            threshold=0.00018,
            source="AXM hm08 secondary-form authoring v0.1",
        )
        targets[f"{side}_nasolabial_crease"] = author_normal_target(
            mesh,
            f"{side}_nasolabial_crease",
            -0.004,
            region=gaussian_region(
                (
                    sign * max(eye_half_sep * 0.42, 0.12),
                    mouth[1] + nose_to_mouth * 0.48,
                    mouth[2] + (landmarks.nose_tip[2] - mouth[2]) * 0.22,
                ),
                (eye_half_sep * 0.20, max(nose_to_mouth * 0.36, 0.095), 0.10),
            ),
            threshold=0.00014,
            source="AXM hm08 secondary-form authoring v0.1",
        )

    return targets


def apply_secondary_forms(
    mesh: Mesh,
    landmarks: Hm08FaceLandmarks,
    eye_metadata: dict[str, object],
    *,
    weights: dict[str, float] | None = None,
    name: str = "hm08_secondary_forms",
) -> tuple[Mesh, dict[str, SparseTarget], dict[str, float]]:
    targets = build_secondary_form_targets(mesh, landmarks, eye_metadata)
    active_weights = {target_name: 1.0 for target_name in targets}
    if weights is not None:
        unknown = sorted(set(weights) - set(targets))
        if unknown:
            raise ValueError(f"unknown secondary-form targets: {unknown}")
        active_weights.update({key: float(value) for key, value in weights.items()})
    output, state = mix_targets(mesh, targets, active_weights, name=name)
    return output, targets, state


def build_preferred_secondary_form_candidate() -> tuple[Mesh, Mesh, dict[str, SparseTarget], Hm08FaceLandmarks, dict[str, object]]:
    base, _ = read_obj_uv(SEED_ROOT / "head.obj", name="hm08_head_v0_2")
    eye_metadata = json.loads((SEED_ROOT / "eye-landmarks.json").read_text(encoding="utf-8"))
    landmarks = derive_hm08_face_landmarks(base, eye_metadata)
    output, targets, state = apply_secondary_forms(base, landmarks, eye_metadata, name="hm08_head_secondary_v0_1")
    return base, output, targets, landmarks, {"target_state": state, "eye_metadata": eye_metadata}


def displacement_report(before: Mesh, after: Mesh) -> dict[str, float | int]:
    if len(before.vertices) != len(after.vertices):
        raise ValueError("secondary form comparison requires identical topology")
    distances = []
    moved = 0
    for a, b in zip(before.vertices, after.vertices):
        distance = sum((b[axis] - a[axis]) ** 2 for axis in range(3)) ** 0.5
        distances.append(distance)
        if distance > 1e-8:
            moved += 1
    moved_distances = [distance for distance in distances if distance > 1e-8]
    return {
        "vertices": len(before.vertices),
        "moved_vertices": moved,
        "mean_moved_distance_raw": sum(moved_distances) / len(moved_distances) if moved_distances else 0.0,
        "max_distance_raw": max(distances, default=0.0),
        "max_distance_mm": max(distances, default=0.0) * 100.0,
    }


if __name__ == "__main__":
    base, output, targets, landmarks, state = build_preferred_secondary_form_candidate()
    print(json.dumps({
        "schema": SCHEMA,
        "targets": {name: len(target.deltas) for name, target in targets.items()},
        "landmarks": {
            "nose_tip": list(landmarks.nose_tip),
            "mouth_center": list(landmarks.mouth_center),
            "chin_center": list(landmarks.chin_center),
        },
        "displacement": displacement_report(base, output),
        "state": state["target_state"],
        "truth": "Low-amplitude reversible AXM-native secondary facial form targets; not a final anatomy-quality claim."
    }, indent=2, sort_keys=True))
