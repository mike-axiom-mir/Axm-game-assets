#!/usr/bin/env python3
from native_hm08_humanoid_rig import build_preferred_hm08_humanoid_rig


def run() -> None:
    body, skeleton, weights, _posed, evidence = build_preferred_hm08_humanoid_rig()
    assert evidence["schema"] == "axm.game-assets.hm08-humanoid-rig.v0.1"
    assert len(body.vertices) == 13380
    assert len(body.faces) == 13378

    skeleton_state = evidence["skeleton"]
    assert skeleton_state["joint_count"] == 23
    assert skeleton_state["skeleton_validation"]["status"] == "pass"
    assert skeleton_state["truth"]["body_derived"] is True
    assert skeleton_state["truth"]["production_autorig_claim"] is False
    names = skeleton_state["joint_names"]
    for required in (
        "pelvis", "spine_lower", "spine_mid", "chest", "neck", "head",
        "left_upper_arm", "left_forearm", "left_hand",
        "right_upper_arm", "right_forearm", "right_hand",
        "left_thigh", "left_shin", "left_foot", "left_toe",
        "right_thigh", "right_shin", "right_foot", "right_toe",
    ):
        assert required in names

    landmarks = skeleton_state["landmarks_m"]
    for left, right in (
        ("left_upper_arm", "right_upper_arm"),
        ("left_forearm", "right_forearm"),
        ("left_hand", "right_hand"),
        ("left_thigh", "right_thigh"),
        ("left_shin", "right_shin"),
        ("left_foot", "right_foot"),
    ):
        a, b = landmarks[left], landmarks[right]
        assert abs(a[0] + b[0]) < 1e-12
        assert abs(a[1] - b[1]) < 1e-12
        assert abs(a[2] - b[2]) < 1e-12

    # Centerline pivots should remain inside plausible body depth rather than
    # sitting on an extreme front/back skin surface.
    for name in ("pelvis", "spine_lower", "spine_mid", "chest", "neck", "head"):
        assert abs(landmarks[name][0]) < 1e-12
        assert -0.11 < landmarks[name][2] < 0.18, (name, landmarks[name])

    skin = evidence["skin"]
    assert skin["validation"]["status"] == "pass"
    assert skin["vertex_count"] == 13380
    assert skin["joint_count"] == 23
    assert skin["max_influences"] == 4
    assert skin["mean_influences"] >= 3.9
    assert len(weights.joints) == len(weights.weights) == 13380
    for row in weights.weights:
        assert abs(sum(row) - 1.0) < 1e-6
        assert sum(value > 1e-8 for value in row) <= 4

    deformation = evidence["deformation"]
    assert deformation["finite"] is True
    assert deformation["truth"]["diagnostic_pose_only"] is True
    assert deformation["truth"]["production_deformation_claim"] is False
    assert deformation["bind_reconstruction_max_error_m"] <= 1e-9, deformation
    assert 0.05 < deformation["posed_max_displacement_m"] < 0.50, deformation
    edge = deformation["edge_ratio"]
    assert edge["p01"] > 0.75, edge
    assert edge["p99"] < 1.20, edge
    assert edge["max"] < 2.50, edge
    assert edge["min"] > 0.15, edge
    assert deformation["edges_over_2x"] <= 16, deformation
    assert deformation["edges_under_half"] <= 16, deformation

    print("HM08 HUMANOID RIG TEST PASS", {
        "joints": len(skeleton.joints),
        "vertices": len(body.vertices),
        "mean_influences": skin["mean_influences"],
        "bind_error_m": deformation["bind_reconstruction_max_error_m"],
        "max_displacement_m": deformation["posed_max_displacement_m"],
        "edge_ratio": edge,
        "edges_over_2x": deformation["edges_over_2x"],
        "edges_under_half": deformation["edges_under_half"],
    })


if __name__ == "__main__":
    run()
