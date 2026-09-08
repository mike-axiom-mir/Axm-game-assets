#!/usr/bin/env python3

from native_hm08_finger_rig import build_preferred_hm08_finger_rig
from native_hm08_humanoid_rig import build_hm08_humanoid_skeleton


def run() -> None:
    body, first_skeleton, first_weights, first_indices, first = build_preferred_hm08_finger_rig()
    _body2, second_skeleton, second_weights, second_indices, second = build_preferred_hm08_finger_rig()
    assert first == second
    assert first_indices == second_indices
    assert first_skeleton.joints == second_skeleton.joints
    assert first_weights.joints == second_weights.joints
    assert first_weights.weights == second_weights.weights

    base, _base_evidence, _base_indices = build_hm08_humanoid_skeleton(body)
    assert len(base.joints) == 23
    assert first_skeleton.joints[:23] == base.joints

    rig = first["rig"]
    skin = first["skin"]
    assert rig["schema"] == "axm.game-assets.hm08-finger-rig.v0.1"
    assert rig["base_joint_count"] == 23
    assert rig["finger_joint_count"] == 30
    assert rig["total_joint_count"] == 53
    assert len(first_skeleton.joints) == 53
    assert len(first_indices) == 30
    assert set(rig["source_side_mapping"]) == {"left", "right"}
    assert set(rig["source_side_mapping"].values()) == {"L", "R"}
    assert rig["skeleton_validation"]["status"] == "pass"
    assert rig["bind_source_pivot_error_m"] < 1e-9
    assert rig["bind_source_tip_error_m"] < 1e-9
    assert rig["source_chain_continuity_gap_m"]["max"] < 0.012, rig["source_chain_continuity_gap_m"]
    assert 0.002 < rig["source_bone_length_m"]["min"] < rig["source_bone_length_m"]["max"] < 0.10
    assert len(rig["tip_local_offsets"]) == 10
    assert rig["truth"]["shared_23_joint_rig_preserved"] is True
    assert rig["truth"]["source_grounded"] is True
    assert rig["truth"]["application_code_imported"] is False
    assert rig["truth"]["production_finger_rig_claim"] is False

    assert skin["schema"] == "axm.game-assets.hm08-finger-skin.v0.1"
    assert skin["base_skin_schema"] == "axm.game-assets.hm08-humanoid-skin.v0.2"
    assert skin["joint_count"] == 53
    assert skin["validation"]["status"] == "pass"
    assert skin["max_influences"] <= 4
    assert skin["overridden_finger_vertices"] > 300, skin
    assert skin["assigned_by_side"]["left"] > 150, skin
    assert skin["assigned_by_side"]["right"] > 150, skin
    assert skin["minimum_vertices_per_segment"] >= 3, skin["assigned_by_segment"]
    assert skin["preserved_nonfinger_rows"] == skin["expected_preserved_nonfinger_rows"]
    assert skin["bind_reconstruction_max_error_m"] < 1e-9
    assert skin["truth"]["shared_body_skin_preserved_outside_fingers"] is True
    assert skin["truth"]["source_grounded_segments"] is True
    assert skin["truth"]["production_finger_skinning_claim"] is False

    print("HM08 SOURCE-GROUNDED FINGER RIG TEST PASS", {
        "joints": rig["total_joint_count"],
        "side_mapping": rig["source_side_mapping"],
        "continuity_gap_mm": rig["source_chain_continuity_gap_m"]["max"] * 1000.0,
        "bone_length_mm": [rig["source_bone_length_m"]["min"]*1000.0, rig["source_bone_length_m"]["max"]*1000.0],
        "finger_vertices": skin["overridden_finger_vertices"],
        "minimum_vertices_per_segment": skin["minimum_vertices_per_segment"],
        "mean_influences": skin["mean_influences"],
    })


if __name__ == "__main__":
    run()
