#!/usr/bin/env python3
from __future__ import annotations

from tempfile import TemporaryDirectory

from native_facial import sample_morph_weight_clip, validate_morph_weight_clip
from native_hm08_face_motion import (
    MAX_AUTHORED_DISPLACEMENT_M,
    TARGET_ORDER,
    build_hm08_face_motion_state,
    write_hm08_face_motion_receipt,
)
from native_morph import apply_morphs, validate_morph_set
from native_targets import mix_targets, validate_target


def run() -> None:
    neutral_a, sparse_a, morphs_a, clips_a, evidence_a = build_hm08_face_motion_state()
    neutral_b, sparse_b, morphs_b, clips_b, evidence_b = build_hm08_face_motion_state()

    assert evidence_a == evidence_b
    assert evidence_a["schema"] == "axm.game-assets.hm08-face-motion.v0.1"
    assert evidence_a["status"] == "pass", evidence_a
    assert neutral_a.vertices == neutral_b.vertices
    assert neutral_a.faces == neutral_b.faces
    assert len(neutral_a.vertices) == 4197
    assert len(neutral_a.faces) == 4168
    assert tuple(sparse_a) == TARGET_ORDER
    assert tuple(sparse_b) == TARGET_ORDER
    assert [target.name for target in morphs_a] == list(TARGET_ORDER)
    assert [target.name for target in morphs_b] == list(TARGET_ORDER)

    # Zero motion must be an exact identity operation over the accepted neutral
    # face. This protects against a facial-motion lane silently replacing the
    # neutral sculpt.
    zero, zero_state = mix_targets(
        neutral_a,
        sparse_a,
        {name: 0.0 for name in TARGET_ORDER},
        name="neutral_zero_motion_test",
    )
    assert zero.vertices == neutral_a.vertices
    assert zero.faces == neutral_a.faces
    assert zero_state["applied"] == []
    assert evidence_a["neutral"]["zero_motion_exact"] is True

    for name in TARGET_ORDER:
        target_a = sparse_a[name]
        target_b = sparse_b[name]
        report = validate_target(target_a, vertex_count=len(neutral_a.vertices))
        assert report["status"] == "pass", report
        assert target_a.deltas == target_b.deltas
        assert len(target_a.deltas) >= 8
        maximum_m = float(evidence_a["targets"][name]["max_displacement_m"])
        assert 0.0 < maximum_m <= MAX_AUTHORED_DISPLACEMENT_M

    # Bilateral channels may differ slightly because real source topology is
    # not required to have perfectly equal sparse row counts, but gross drift
    # would indicate a broken landmark/mask route.
    assert float(evidence_a["pair_coverage_ratio"]["blink"]) >= 0.75
    assert float(evidence_a["pair_coverage_ratio"]["brow_raise"]) >= 0.75

    morph_report = validate_morph_set(morphs_a, vertex_count=len(neutral_a.vertices))
    assert morph_report["status"] == "pass", morph_report

    # Meter-space morph application must move geometry while preserving the
    # canonical face topology.
    blink_weights = [0.0] * len(TARGET_ORDER)
    blink_weights[TARGET_ORDER.index("left_blink")] = 1.0
    blinked = apply_morphs(neutral_a, morphs_a, blink_weights, name="left_blink_meter_test")
    assert blinked.faces == neutral_a.faces
    assert sum(a != b for a, b in zip(neutral_a.vertices, blinked.vertices)) >= 8

    assert len(clips_a) == 3
    assert [clip.name for clip in clips_a] == ["blink_test", "smile_test", "jaw_open_test"]
    for clip in clips_a:
        report = validate_morph_weight_clip(clip, len(TARGET_ORDER))
        assert report["status"] == "pass", report

    blink_peak = sample_morph_weight_clip(clips_a[0], 0.08)
    assert blink_peak[TARGET_ORDER.index("left_blink")] == 1.0
    assert blink_peak[TARGET_ORDER.index("right_blink")] == 1.0
    assert sum(blink_peak) == 2.0

    smile_peak = sample_morph_weight_clip(clips_a[1], 0.35)
    assert smile_peak[TARGET_ORDER.index("smile")] == 0.80
    assert sum(smile_peak) == 0.80

    jaw_peak = sample_morph_weight_clip(clips_a[2], 0.25)
    assert jaw_peak[TARGET_ORDER.index("jaw_open")] == 0.70
    assert sum(jaw_peak) == 0.70

    with TemporaryDirectory() as first, TemporaryDirectory() as second:
        receipt_a = write_hm08_face_motion_receipt(first)
        receipt_b = write_hm08_face_motion_receipt(second)
        assert receipt_a == receipt_b
        assert receipt_a["status"] == "pass"
        assert receipt_a["target_count"] == len(TARGET_ORDER)
        assert receipt_a["clip_count"] == 3
        assert receipt_a["receipt_sha256"] == receipt_b["receipt_sha256"]
        assert receipt_a["truth"]["neutral_identity_replaced"] is False
        assert receipt_a["truth"]["visual_promotion"] is False

    print(
        "HM08 FACE MOTION TEST PASS",
        {
            "vertices": len(neutral_a.vertices),
            "faces": len(neutral_a.faces),
            "targets": len(TARGET_ORDER),
            "clips": len(clips_a),
            "blink_pair_coverage": evidence_a["pair_coverage_ratio"]["blink"],
            "brow_pair_coverage": evidence_a["pair_coverage_ratio"]["brow_raise"],
            "max_displacement_mm": max(
                float(row["max_displacement_mm"])
                for row in evidence_a["targets"].values()
            ),
        },
    )


if __name__ == "__main__":
    run()
