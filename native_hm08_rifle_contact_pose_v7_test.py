#!/usr/bin/env python3

from native_hm08_rifle_contact_pose_v6 import MAX_TIP_PENETRATION_M, SURFACE_CLEARANCE_M
from native_hm08_rifle_contact_pose_v7 import PALM_SURFACE_CLEARANCE_M, build_preferred_physical_grip_rifle_contact_pose


def run() -> None:
    first_mesh, first = build_preferred_physical_grip_rifle_contact_pose()
    second_mesh, second = build_preferred_physical_grip_rifle_contact_pose()
    assert first == second
    assert first_mesh.vertices == second_mesh.vertices
    assert first_mesh.faces == second_mesh.faces
    assert all(first["acceptance"].values()), first["acceptance"]

    assert first["schema"] == "axm.game-assets.hm08-rifle-contact-pose.v0.7"
    assert first["pose_id"] == "cross_chest_physical_palm_surface_grip_v0.7"
    assert first["weapon"]["scale"] == [1.0, 1.0, 1.0]
    assert first["shared_rig"]["joint_count"] == 53
    assert first["shared_rig"]["finger_joint_count"] == 30
    assert first["truth"]["human_scale_rifle_world_transform_preserved"] is True
    assert first["truth"]["v0_4_center_socket_contact_superseded_for_physical_grip"] is True
    assert first["truth"]["production_grip_claim"] is False

    palm = first["surface_palm_contact"]
    assert palm["changed_variable_from_v0_4"] == "hand_contact_semantics_center_socket_to_near_physical_grip_surface"
    assert abs(palm["palm_surface_clearance_m"] - PALM_SURFACE_CLEARANCE_M) < 1e-12
    assert palm["maximum_target_error_m"] < 1e-8
    assert palm["old_center_socket_separation_m_range"][0] > 0.020
    for side in ("right", "left"):
        row = palm["rows"][side]
        assert row["weapon_component"] in ("primary_grip", "foregrip")
        assert row["surface_target_error_m"] < 1e-8
        assert row["old_center_socket_separation_m"] > 0.020
        assert row["reach_m"] <= row["maximum_reach_m"] + 1e-9
        assert abs(row["resolved_palm_surface_gap"]["surface_gap_m"] - PALM_SURFACE_CLEARANCE_M) < 0.008

    grip = first["finger_grip"]
    assert grip["changed_variable_from_v0_6"] == "palm_start_state_center_socket_to_physical_near_surface_before_same_far_surface_finger_objective"
    assert grip["v0_5_visual_status"] == "rejected_real_godot_hand_close_crushed_twisted_fingers"
    assert grip["v0_6_native_status"] == "rejected_no_collision_safe_pinky_candidate_from_center_socket_palm_state"
    assert abs(grip["surface_clearance_m"] - SURFACE_CLEARANCE_M) < 1e-12
    assert abs(grip["maximum_tip_penetration_m"] - MAX_TIP_PENETRATION_M) < 1e-12
    assert grip["minimum_target_improvement_m"] > 1e-6
    assert grip["mean_target_improvement_m"] > grip["minimum_target_improvement_m"]
    assert grip["max_deep_tip_penetration_m"] <= MAX_TIP_PENETRATION_M + 1e-12
    assert grip["nonfinger_curl_max_displacement_m"] < 1e-8
    for side in ("right", "left"):
        row = grip["choices"][side]
        assert row["curled_target_mean_m"] < row["open_target_mean_m"], row
        for digit, digit_row in row["digits"].items():
            assert digit_row["safe_candidate_count"] > 0, (side, digit, digit_row)
            assert digit_row["selected_tip_penetration_m"] <= MAX_TIP_PENETRATION_M + 1e-12
            assert digit_row["curled_tip_to_surface_target_m"] < digit_row["open_tip_to_surface_target_m"]
            assert digit_row["improvement_m"] > 1e-6

    print("HM08 PHYSICAL GRIP V0.7 TEST PASS", {
        "palm_center_to_surface_shift_mm": [value * 1000.0 for value in palm["old_center_socket_separation_m_range"]],
        "palm_surface_gap_mm": [value * 1000.0 for value in palm["resolved_palm_surface_gap_m_range"]],
        "minimum_finger_target_improvement_mm": grip["minimum_target_improvement_m"] * 1000.0,
        "mean_finger_target_improvement_mm": grip["mean_target_improvement_m"] * 1000.0,
        "tip_surface_gap_mm_range": [value * 1000.0 for value in grip["final_tip_surface_gap_m_range"]],
        "max_tip_penetration_mm": grip["max_deep_tip_penetration_m"] * 1000.0,
        "max_curl_mm": grip["finger_curl_max_displacement_m"] * 1000.0,
    })


if __name__ == "__main__":
    run()
