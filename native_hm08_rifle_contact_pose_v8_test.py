#!/usr/bin/env python3

from native_hm08_rifle_contact_pose_v6 import MAX_TIP_PENETRATION_M
from native_hm08_rifle_contact_pose_v8 import (
    MAX_FINAL_PALM_NORMAL_ERROR_DEG,
    MAX_PALM_CORRECTION_DEG,
    MAX_ROOT_PENETRATION_M,
    build_preferred_palm_aligned_rifle_contact_pose,
)


def run() -> None:
    first_mesh, first = build_preferred_palm_aligned_rifle_contact_pose()
    second_mesh, second = build_preferred_palm_aligned_rifle_contact_pose()
    assert first == second
    assert first_mesh.vertices == second_mesh.vertices
    assert first_mesh.faces == second_mesh.faces
    assert all(first["acceptance"].values()), first["acceptance"]

    assert first["schema"] == "axm.game-assets.hm08-rifle-contact-pose.v0.8"
    assert first["pose_id"] == "cross_chest_palm_plane_aligned_physical_grip_v0.8"
    assert first["weapon"]["scale"] == [1.0, 1.0, 1.0]
    assert first["shared_rig"]["joint_count"] == 53
    assert first["shared_rig"]["finger_joint_count"] == 30
    assert first["truth"]["source_grounded_palm_plane"] is True
    assert first["truth"]["human_scale_rifle_world_transform_preserved"] is True
    assert first["truth"]["production_grip_claim"] is False

    palm = first["surface_palm_contact"]
    assert palm["changed_variable_from_v0_7"] == "wrist_world_orientation_align_source_grounded_palm_plane_to_grip_inward_normal"
    assert palm["maximum_target_error_m"] < 1e-8
    assert palm["old_center_socket_separation_m_range"][0] > 0.020
    assert palm["first_pass_palm_normal_error_deg_range"][0] > 65.0
    assert palm["final_palm_normal_error_deg_range"][1] <= MAX_FINAL_PALM_NORMAL_ERROR_DEG
    assert palm["orientation_correction_deg_range"][1] <= MAX_PALM_CORRECTION_DEG
    assert palm["max_proximal_root_penetration_m"] <= MAX_ROOT_PENETRATION_M
    for side in ("right", "left"):
        row = palm["rows"][side]
        assert row["surface_target_error_m"] < 1e-8
        assert row["first_pass"]["palm_normal_error_deg"] > 65.0
        assert row["final_palm_normal_error_deg"] <= MAX_FINAL_PALM_NORMAL_ERROR_DEG
        assert row["orientation_correction"]["angle_deg"] <= MAX_PALM_CORRECTION_DEG
        assert row["reach_m"] <= row["maximum_reach_m"] + 1e-9
        assert set(row["proximal_finger_roots"]) == {"1", "2", "3", "4", "5"}
        for digit, root in row["proximal_finger_roots"].items():
            assert root["surface_gap"]["surface_gap_m"] >= -MAX_ROOT_PENETRATION_M - 1e-12, (side, digit, root)

    grip = first["finger_grip"]
    assert grip["changed_variable_from_v0_7"] == "palm_plane_alignment_before_collision_bounded_far_surface_finger_wrap"
    assert grip["v0_5_visual_status"] == "rejected_real_godot_hand_close_crushed_twisted_fingers"
    assert grip["v0_6_native_status"] == "rejected_no_collision_safe_pinky_candidate_from_center_socket_palm_state"
    assert grip["v0_7_native_status"] == "rejected_palm_surface_position_correct_but_palm_plane_about_70_to_73_degrees_edge_on"
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

    print("HM08 PALM-ALIGNED PHYSICAL GRIP V0.8 TEST PASS", {
        "first_pass_palm_error_deg": palm["first_pass_palm_normal_error_deg_range"],
        "final_palm_error_deg": palm["final_palm_normal_error_deg_range"],
        "orientation_correction_deg": palm["orientation_correction_deg_range"],
        "proximal_root_gap_mm_range": [value * 1000.0 for value in palm["proximal_root_surface_gap_m_range"]],
        "minimum_finger_target_improvement_mm": grip["minimum_target_improvement_m"] * 1000.0,
        "mean_finger_target_improvement_mm": grip["mean_target_improvement_m"] * 1000.0,
        "tip_surface_gap_mm_range": [value * 1000.0 for value in grip["final_tip_surface_gap_m_range"]],
        "max_tip_penetration_mm": grip["max_deep_tip_penetration_m"] * 1000.0,
        "max_curl_mm": grip["finger_curl_max_displacement_m"] * 1000.0,
    })


if __name__ == "__main__":
    run()
