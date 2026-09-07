#!/usr/bin/env python3
from native_pbr import png_bytes
from native_visual_evidence import (
    CriterionObservation,
    build_capture_packet,
    build_observation_packet,
    summarize_observation,
    validate_capture_packet,
)


def run() -> None:
    pixels = bytes([
        8, 10, 16,   8, 10, 16,
        8, 10, 16,   180, 92, 44,
    ])
    png = png_bytes(2, 2, 3, pixels)
    capture = build_capture_packet(
        png,
        asset_digest="sha256:" + "1" * 64,
        engine={"name": "Godot", "version": "4.7.2"},
        camera={"position": [1.0, 0.5, 1.0], "fov": 42.0},
        render_settings={"renderer": "gl_compatibility", "size": [2, 2]},
        metrics={"foreground_coverage": 0.25, "luma_range": 0.4},
        source_receipts=["sha256:" + "2" * 64],
    )
    assert capture["authority"] == "deterministic_capture_fact"
    assert capture["image"]["width"] == 2 and capture["image"]["height"] == 2
    assert validate_capture_packet(capture, png)["status"] == "pass"

    changed = png_bytes(2, 2, 3, bytes([0] * 12))
    assert validate_capture_packet(capture, changed)["status"] == "fail"

    observation = build_observation_packet(
        capture["capture_digest"],
        [
            CriterionObservation("silhouette_readability", 0.8, 0.9, "Readable at this camera."),
            CriterionObservation("material_response", 0.6, 0.7, "Some separation visible."),
            CriterionObservation("facial_quality", None, 0.95, "Not visible in this weapon capture."),
        ],
        observer={"type": "test_fixture", "id": "observer-v0"},
        rubric_id="axm-close-inspection-v0",
    )
    assert observation["authority"] == "advisory_observation"
    assert observation["truth"]["automatic_canon"] is False
    summary = summarize_observation(observation)
    expected = (0.8 * 0.9 + 0.6 * 0.7) / (0.9 + 0.7)
    assert abs(summary["confidence_weighted_score"] - expected) < 1e-12
    assert summary["scored_criteria"] == 2 and summary["unscored_criteria"] == 1
    assert summary["automatic_canon"] is False
    print("NATIVE VISUAL EVIDENCE TEST PASS", capture["capture_digest"], observation["observation_digest"], summary)


if __name__ == "__main__":
    run()
