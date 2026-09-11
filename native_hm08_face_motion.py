#!/usr/bin/env python3
"""Deterministic source-grounded motion targets for the preferred hm08 face.

This module adds a first reversible facial-motion layer to the accepted neutral
Sentinel identity. It does not replace the neutral face and it does not claim
final production facial-animation quality. Every motion channel is authored as
sparse fixed-topology deltas over the repaired hm08 head, then converted to the
existing native morph-weight representation for later engine delivery.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Callable

from native_facial import MorphWeightClip, validate_morph_weight_clip
from native_geometry import Mesh
from native_hm08_face_eyes import RAW_TO_M, SEED_ROOT
from native_hm08_face_proof import DEFAULT_WEIGHTS
from native_hm08_landmarks import Hm08FaceLandmarks, derive_hm08_face_landmarks, landmark_packet
from native_morph import MorphTarget, validate_morph_set
from native_target_authoring import author_custom_target, author_offset_target, gaussian_region
from native_targets import SparseTarget, load_target, mix_targets, target_digest, to_morph_target, validate_target
from native_uv import read_obj_uv

SCHEMA = "axm.game-assets.hm08-face-motion.v0.1"
TARGET_ORDER = (
    "left_blink",
    "right_blink",
    "left_brow_raise",
    "right_brow_raise",
    "smile",
    "frown",
    "jaw_open",
)
MAX_AUTHORED_DISPLACEMENT_M = 0.0045
MIN_TARGET_ROWS = 8

WeightFn = Callable[[int, tuple[float, float, float]], float]


def _sha(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _load_neutral_identity() -> tuple[Mesh, Hm08FaceLandmarks, dict[str, object], dict[str, object]]:
    raw_head, _head_uv = read_obj_uv(SEED_ROOT / "head.obj", name="hm08_head_v0_2")
    library = {
        name: load_target(SEED_ROOT / "targets" / f"{name}.target", license="CC0-source-remap")
        for name in sorted(DEFAULT_WEIGHTS)
    }
    neutral, identity_state = mix_targets(
        raw_head,
        library,
        DEFAULT_WEIGHTS,
        name="sentinel_hm08_face_neutral_motion_source",
    )
    eye_metadata = json.loads((SEED_ROOT / "eye-landmarks.json").read_text(encoding="utf-8"))
    landmarks = derive_hm08_face_landmarks(neutral, eye_metadata)
    return neutral, landmarks, eye_metadata, identity_state


def _masked_region(base: WeightFn, predicate: Callable[[tuple[float, float, float]], bool]) -> WeightFn:
    def weight(index: int, point: tuple[float, float, float]) -> float:
        if not predicate(point):
            return 0.0
        return float(base(index, point))
    return weight


def _scale_sparse_target(target: SparseTarget, scale: float) -> SparseTarget:
    return SparseTarget(
        name=target.name,
        deltas={index: tuple(value * scale for value in delta) for index, delta in target.deltas.items()},
        source=target.source,
        license=target.license,
        metadata={**target.metadata, "coordinate_scale": scale, "coordinate_space": "meters"},
    )


def _max_displacement_m(target: SparseTarget) -> float:
    if not target.deltas:
        return 0.0
    return max(math.sqrt(sum(value * value for value in delta)) for delta in target.deltas.values()) * RAW_TO_M


def _coverage_ratio(a: SparseTarget, b: SparseTarget) -> float:
    high = max(len(a.deltas), len(b.deltas))
    low = min(len(a.deltas), len(b.deltas))
    return (low / high) if high else 0.0


def build_hm08_face_motion_targets(
    mesh: Mesh,
    landmarks: Hm08FaceLandmarks,
    eye_metadata: dict[str, object],
) -> dict[str, SparseTarget]:
    """Author bounded reversible motion targets in canonical raw hm08 space."""
    eye_y = (landmarks.left_eye[1] + landmarks.right_eye[1]) * 0.5
    eye_half_sep = abs(landmarks.left_eye[0] - landmarks.right_eye[0]) * 0.5
    eye_to_nose = eye_y - landmarks.nose_tip[1]
    nose_to_mouth = landmarks.nose_tip[1] - landmarks.mouth_center[1]
    eye_front_z = (
        (landmarks.left_eye[2] + landmarks.right_eye[2]) * 0.5
        + float(eye_metadata["prototype_eye_radius_raw"]) * 0.82
    )
    mouth = landmarks.mouth_center
    chin = landmarks.chin_center

    if eye_half_sep <= 0.05 or eye_to_nose <= 0.05 or nose_to_mouth <= 0.03:
        raise ValueError("unexpected hm08 facial proportions for motion authoring")

    targets: dict[str, SparseTarget] = {}

    # Blink targets pull upper/lower eyelid surface toward the source-grounded
    # eye center. A narrow front-face predicate prevents broad temple/brow drag.
    for side, eye in (("left", landmarks.left_eye), ("right", landmarks.right_eye)):
        base = gaussian_region(
            (eye[0], eye_y, eye_front_z),
            (eye_half_sep * 0.43, eye_to_nose * 0.17, 0.095),
        )
        region = _masked_region(
            base,
            lambda point, ex=eye[0]: (
                abs(point[0] - ex) <= eye_half_sep * 0.60
                and abs(point[1] - eye_y) <= eye_to_nose * 0.24
                and point[2] >= eye_front_z - 0.13
            ),
        )

        def blink_offset(_index, point, _normal):
            dy = max(-0.018, min(0.018, (eye_y - point[1]) * 0.62))
            # A small inward component keeps the closure from reading as a
            # paper flap while remaining intentionally conservative.
            return (0.0, dy, -0.0035)

        targets[f"{side}_blink"] = author_custom_target(
            mesh,
            f"{side}_blink",
            region=region,
            offset_fn=blink_offset,
            threshold=0.00010,
            source="AXM hm08 geometry-grounded face-motion authoring v0.1",
        )

    # Brow raise stays separate per side so later acting can be asymmetric.
    for side, eye in (("left", landmarks.left_eye), ("right", landmarks.right_eye)):
        region = gaussian_region(
            (eye[0], eye_y + eye_to_nose * 0.31, eye_front_z - 0.020),
            (eye_half_sep * 0.55, eye_to_nose * 0.28, 0.15),
        )
        targets[f"{side}_brow_raise"] = author_offset_target(
            mesh,
            f"{side}_brow_raise",
            (0.0, 0.018, 0.0020),
            region=region,
            threshold=0.00010,
            source="AXM hm08 geometry-grounded face-motion authoring v0.1",
        )

    mouth_radius = (
        eye_half_sep * 0.86,
        max(nose_to_mouth * 0.25, 0.080),
        0.13,
    )
    mouth_region = gaussian_region(mouth, mouth_radius)
    corner_scale = max(eye_half_sep * 0.68, 1e-6)

    def smile_offset(_index, point, _normal):
        relative_x = point[0] - mouth[0]
        corner = min(1.0, abs(relative_x) / corner_scale)
        sign = -1.0 if relative_x < 0.0 else 1.0
        return (
            sign * 0.010 * corner,
            0.003 * (1.0 - corner) + 0.018 * corner,
            0.0025,
        )

    targets["smile"] = author_custom_target(
        mesh,
        "smile",
        region=mouth_region,
        offset_fn=smile_offset,
        threshold=0.00010,
        source="AXM hm08 geometry-grounded face-motion authoring v0.1",
    )

    def frown_offset(_index, point, _normal):
        relative_x = point[0] - mouth[0]
        corner = min(1.0, abs(relative_x) / corner_scale)
        sign = -1.0 if relative_x < 0.0 else 1.0
        return (
            -sign * 0.004 * corner,
            -0.014 * corner,
            -0.0010,
        )

    targets["frown"] = author_custom_target(
        mesh,
        "frown",
        region=mouth_region,
        offset_fn=frown_offset,
        threshold=0.00010,
        source="AXM hm08 geometry-grounded face-motion authoring v0.1",
    )

    jaw_center = (
        (mouth[0] + chin[0]) * 0.5,
        (mouth[1] + chin[1]) * 0.5,
        (mouth[2] + chin[2]) * 0.5,
    )
    jaw_region_base = gaussian_region(
        jaw_center,
        (eye_half_sep * 0.92, max(eye_to_nose * 0.70, 0.22), 0.19),
    )
    jaw_region = _masked_region(
        jaw_region_base,
        lambda point: point[1] <= mouth[1] + max(nose_to_mouth * 0.12, 0.025),
    )
    jaw_span = max(mouth[1] - chin[1], 1e-6)

    def jaw_open_offset(_index, point, _normal):
        lower = max(0.0, min(1.0, (mouth[1] - point[1]) / jaw_span))
        return (0.0, -(0.012 + 0.022 * lower), -0.004 * lower)

    targets["jaw_open"] = author_custom_target(
        mesh,
        "jaw_open",
        region=jaw_region,
        offset_fn=jaw_open_offset,
        threshold=0.00010,
        source="AXM hm08 geometry-grounded face-motion authoring v0.1",
    )

    if tuple(targets) != TARGET_ORDER:
        raise ValueError(f"face-motion target order drifted: {tuple(targets)}")
    return targets


def build_hm08_face_motion_clips() -> list[MorphWeightClip]:
    index = {name: position for position, name in enumerate(TARGET_ORDER)}

    def row(**weights: float) -> tuple[float, ...]:
        values = [0.0] * len(TARGET_ORDER)
        for name, value in weights.items():
            if name not in index:
                raise ValueError(f"unknown face-motion target {name}")
            values[index[name]] = float(value)
        return tuple(values)

    return [
        MorphWeightClip(
            "blink_test",
            [0.0, 0.08, 0.16],
            [row(), row(left_blink=1.0, right_blink=1.0), row()],
        ),
        MorphWeightClip(
            "smile_test",
            [0.0, 0.35, 0.70],
            [row(), row(smile=0.80), row()],
        ),
        MorphWeightClip(
            "jaw_open_test",
            [0.0, 0.25, 0.50],
            [row(), row(jaw_open=0.70), row()],
        ),
    ]


def build_hm08_face_motion_state() -> tuple[
    Mesh,
    dict[str, SparseTarget],
    list[MorphTarget],
    list[MorphWeightClip],
    dict[str, object],
]:
    neutral, landmarks, eye_metadata, identity_state = _load_neutral_identity()
    targets = build_hm08_face_motion_targets(neutral, landmarks, eye_metadata)

    failures: list[str] = []
    target_rows: dict[str, object] = {}
    meter_targets: list[MorphTarget] = []
    for name in TARGET_ORDER:
        target = targets[name]
        report = validate_target(target, vertex_count=len(neutral.vertices))
        maximum = _max_displacement_m(target)
        if report["status"] != "pass":
            failures.append(f"{name}: invalid sparse target {report['failures']}")
        if len(target.deltas) < MIN_TARGET_ROWS:
            failures.append(f"{name}: moves only {len(target.deltas)} vertices")
        if maximum <= 0.0 or maximum > MAX_AUTHORED_DISPLACEMENT_M:
            failures.append(f"{name}: max displacement {maximum:.6f}m outside bounded envelope")
        target_rows[name] = {
            "rows": len(target.deltas),
            "digest": target_digest(target),
            "max_displacement_m": maximum,
            "max_displacement_mm": maximum * 1000.0,
        }
        meter_sparse = _scale_sparse_target(target, RAW_TO_M)
        meter_targets.append(to_morph_target(meter_sparse, vertex_count=len(neutral.vertices)))

    pair_coverage = {
        "blink": _coverage_ratio(targets["left_blink"], targets["right_blink"]),
        "brow_raise": _coverage_ratio(targets["left_brow_raise"], targets["right_brow_raise"]),
    }
    if pair_coverage["blink"] < 0.75:
        failures.append(f"blink target coverage asymmetry too high: {pair_coverage['blink']:.3f}")
    if pair_coverage["brow_raise"] < 0.75:
        failures.append(f"brow target coverage asymmetry too high: {pair_coverage['brow_raise']:.3f}")

    morph_report = validate_morph_set(meter_targets, vertex_count=len(neutral.vertices))
    if morph_report["status"] != "pass":
        failures.append(f"meter-space morph target validation failed: {morph_report['failures']}")

    clips = build_hm08_face_motion_clips()
    clip_reports = [validate_morph_weight_clip(clip, len(TARGET_ORDER)) for clip in clips]
    for report in clip_reports:
        if report["status"] != "pass":
            failures.append(f"clip {report['name']} invalid: {report['failures']}")

    # Applying an all-zero target map must reproduce the accepted neutral mesh
    # exactly. This is the non-destructive identity boundary for this lane.
    zero_neutral, zero_state = mix_targets(
        neutral,
        targets,
        {name: 0.0 for name in TARGET_ORDER},
        name="sentinel_hm08_face_neutral_zero_motion",
    )
    neutral_exact = zero_neutral.vertices == neutral.vertices and zero_neutral.faces == neutral.faces
    if not neutral_exact:
        failures.append("zero motion does not reproduce neutral identity exactly")

    neutral_payload = json.dumps(
        {"vertices": neutral.vertices, "faces": neutral.faces},
        separators=(",", ":"),
    ).encode("utf-8")
    evidence: dict[str, object] = {
        "schema": SCHEMA,
        "status": "pass" if not failures else "fail",
        "failures": failures,
        "neutral": {
            "vertices": len(neutral.vertices),
            "faces": len(neutral.faces),
            "sha256": _sha(neutral_payload),
            "zero_motion_exact": neutral_exact,
            "zero_motion_state": zero_state,
            "identity_target_mix": identity_state,
        },
        "landmarks": landmark_packet(landmarks),
        "target_order": list(TARGET_ORDER),
        "targets": target_rows,
        "pair_coverage_ratio": pair_coverage,
        "meter_morph_validation": morph_report,
        "clips": clip_reports,
        "bounds": {
            "max_authored_displacement_m": MAX_AUTHORED_DISPLACEMENT_M,
            "raw_to_meter_scale": RAW_TO_M,
        },
        "truth": {
            "neutral_identity_replaced": False,
            "topology_changed": False,
            "source_grounded": True,
            "visual_promotion": False,
            "production_facial_rig_claim": False,
            "notes": [
                "Eye centers are pinned hm08 source metadata; nose/mouth/chin are existing AXM geometry-grounded authoring landmarks.",
                "Motion channels are reversible AXM-authored deltas over the accepted neutral identity, not destructive mesh edits.",
                "Structural validation does not prove FACS accuracy, lip seal, eyelid/cornea contact, acting quality or cinematic wrinkle behavior.",
            ],
        },
    }
    if failures:
        raise ValueError(f"hm08 face-motion gates failed: {evidence}")
    return neutral, targets, meter_targets, clips, evidence


def write_hm08_face_motion_receipt(output: str | Path) -> dict[str, object]:
    root = Path(output)
    root.mkdir(parents=True, exist_ok=True)
    _neutral, _targets, _meter_targets, _clips, evidence = build_hm08_face_motion_state()
    payload = (json.dumps(evidence, indent=2, sort_keys=True) + "\n").encode("utf-8")
    path = root / "hm08-face-motion-receipt.json"
    path.write_bytes(payload)
    return {
        "schema": SCHEMA,
        "receipt": path.name,
        "receipt_sha256": _sha(payload),
        "status": evidence["status"],
        "target_count": len(TARGET_ORDER),
        "clip_count": len(evidence["clips"]),
        "truth": evidence["truth"],
    }


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("output", nargs="?", default="build/hm08-face-motion")
    args = parser.parse_args()
    print(json.dumps(write_hm08_face_motion_receipt(args.output), indent=2, sort_keys=True))
