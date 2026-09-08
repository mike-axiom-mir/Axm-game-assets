#!/usr/bin/env python3

from native_hm08_finger_grip_pose_v2 import build_preferred_hm08_finger_grip_pose_v2


def run() -> None:
    first_mesh, first = build_preferred_hm08_finger_grip_pose_v2()
    second_mesh, second = build_preferred_hm08_finger_grip_pose_v2()
    assert first == second
    assert first_mesh.vertices == second_mesh.vertices
    assert first_mesh.faces == second_mesh.faces

    assert first["schema"] == "axm.game-assets.hm08-finger-grip-pose.v0.2"
    assert first["pose_id"] == "source_grounded_rifle_grip_v0.2"
    assert first["repair_lineage"]["v0_1_status"] == "rejected_coordinate_space_bug_in_thumb_opposition"
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
        assert len(first["curl_search"][side]["candidate_objectives"]) == 8
        thumb = first["curl_search"][side]["thumb"]
        assert thumb["coordinate_space"] == "hand_joint_local"
        assert thumb["tip_to_grip_center_m"] < 0.18, thumb
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
    assert first["truth"]["thumb_coordinate_space_corrected"] is True
    assert first["truth"]["trigger_finger_claim"] is False
    assert first["truth"]["production_grip_claim"] is False
    assert first["truth"]["automatic_visual_promotion"] is False

    print("HM08 ARTICULATED RIFLE GRIP V0.2 TEST PASS", {
        "joints": first["finger_rig"]["total_joint_count"],
        "finger_vertices": first["finger_skin"]["overridden_finger_vertices"],
        "finger_changed_vertices": first["finger_changed_vertices"],
        "right_curl": first["curl_search"]["right"]["selected"],
        "left_curl": first["curl_search"]["left"]["selected"],
        "right_thumb": first["curl_search"]["right"]["thumb"],
        "left_thumb": first["curl_search"]["left"]["thumb"],
    })


if __name__ == "__main__":
    run()
