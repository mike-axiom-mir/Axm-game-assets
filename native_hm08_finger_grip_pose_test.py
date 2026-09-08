#!/usr/bin/env python3

from native_hm08_finger_grip_pose import build_preferred_hm08_finger_grip_pose


def run() -> None:
    first_mesh, first = build_preferred_hm08_finger_grip_pose()
    second_mesh, second = build_preferred_hm08_finger_grip_pose()
    assert first == second
    assert first_mesh.vertices == second_mesh.vertices
    assert first_mesh.faces == second_mesh.faces

    assert first["schema"] == "axm.game-assets.hm08-finger-grip-pose.v0.1"
    assert first["pose_id"] == "source_grounded_rifle_grip_v0.1"
    assert first["changed_variable_from_v0_4"] == "finger_skeleton_weights_and_grip_closure_only"
    assert first["finger_rig"]["total_joint_count"] == 53
    assert first["finger_rig"]["skeleton_validation"]["status"] == "pass"
    assert first["finger_skin"]["validation"]["status"] == "pass"
    assert first["finger_skin"]["max_influences"] <= 4
    assert first["finger_changed_vertices"] > 200, first["finger_changed_vertices"]
    assert first["nonfinger_max_delta_from_v0_4_m"] < 1e-8, first["nonfinger_max_delta_from_v0_4_m"]

    contact = first["contact"]
    assert contact["primary_position_error"] < 1e-8, contact
    assert contact["support_position_error"] < 1e-6, contact
    assert contact["primary_orientation_error_deg"] < 1e-5, contact
    assert contact["support_orientation_error_deg"] < 1e-4, contact

    for side in ("right", "left"):
        selected = first["curl_search"][side]["selected"]
        assert selected["sign"] in (-1.0, 1.0)
        assert selected["multiplier"] in (0.70, 0.85, 1.00, 1.15)
        assert selected["objective"] >= 0.0
        assert len(first["curl_search"][side]["candidate_objectives"]) == 8
        assert first["curl_search"][side]["thumb"]["tip_to_grip_center_m"] < 0.18
        for digit in (2, 3, 4, 5):
            tip = first["final_fingertips"][side][str(digit)]
            assert tip["radius_error_m"] < 0.080, (side, digit, tip)
            assert abs(tip["axis_offset_m"]) < 0.20, (side, digit, tip)

    assert first["weapon"]["design_schema"] == "axm.game-assets.sentinel-rifle-human-scale.v0.5"
    assert first["weapon"]["scale"] == [1.0, 1.0, 1.0]
    assert first["truth"]["v0_4_arm_pose_preserved"] is True
    assert first["truth"]["human_scale_rifle_preserved"] is True
    assert first["truth"]["palm_socket_contact_preserved"] is True
    assert first["truth"]["source_grounded_finger_pivots"] is True
    assert first["truth"]["trigger_finger_claim"] is False
    assert first["truth"]["production_grip_claim"] is False
    assert first["truth"]["automatic_visual_promotion"] is False

    print("HM08 ARTICULATED RIFLE GRIP TEST PASS", {
        "joints": first["finger_rig"]["total_joint_count"],
        "finger_vertices": first["finger_skin"]["overridden_finger_vertices"],
        "finger_changed_vertices": first["finger_changed_vertices"],
        "right_curl": first["curl_search"]["right"]["selected"],
        "left_curl": first["curl_search"]["left"]["selected"],
        "primary_error_mm": contact["primary_position_error"]*1000.0,
        "support_error_mm": contact["support_position_error"]*1000.0,
    })


if __name__ == "__main__":
    run()
