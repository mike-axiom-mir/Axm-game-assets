#!/usr/bin/env python3

from native_hm08_rifle_contact_pose_v6 import (
    SURFACE_CLEARANCE_M,
    build_preferred_grip_volume_rifle_contact_pose,
)


def run() -> None:
    first_mesh, first = build_preferred_grip_volume_rifle_contact_pose()
    second_mesh, second = build_preferred_grip_volume_rifle_contact_pose()
    assert first == second
    assert first_mesh.vertices == second_mesh.vertices
    assert first_mesh.faces == second_mesh.faces
    assert all(first["acceptance"].values()), first["acceptance"]

    assert first["schema"] == "axm.game-assets.hm08-rifle-contact-pose.v0.6"
    assert first["pose_id"] == "cross_chest_low_ready_grip_volume_v0.6"
    assert first["shared_rig"]["joint_count"] == 53
    assert first["shared_rig"]["finger_joint_count"] == 30
    assert first["weapon"]["scale"] == [1.0, 1.0, 1.0]
    assert first["truth"]["real_weapon_grip_volume_used"] is True
    assert first["truth"]["v0_5_visual_result_promoted"] is False
    assert first["truth"]["production_grip_claim"] is False
    grip = first["finger_grip"]
    assert grip["changed_variable_from_v0_5"] == "target_geometry_socket_center_to_real_component_surface_volume"
    assert grip["v0_5_visual_status"] == "rejected_real_godot_hand_close_crushed_twisted_fingers"
    assert abs(grip["surface_clearance_m"] - SURFACE_CLEARANCE_M) < 1e-12
    assert grip["minimum_target_improvement_m"] > 1e-6
    assert grip["mean_target_improvement_m"] > grip["minimum_target_improvement_m"]
    assert grip["max_deep_tip_penetration_m"] < 0.018
    assert grip["nonfinger_curl_max_displacement_m"] < 1e-8
    assert grip["head_curl_max_displacement_m"] < 1e-9
    assert grip["lower_body_curl_max_displacement_m"] < 1e-9

    assert set(grip["choices"]) == {"right", "left"}
    assert grip["choices"]["right"]["volume"]["name"] == "primary_grip"
    assert grip["choices"]["left"]["volume"]["name"] == "foregrip"
    for side in ("right", "left"):
        row = grip["choices"][side]
        assert row["curled_target_mean_m"] < row["open_target_mean_m"], row
        assert row["mean_improvement_m"] > 0.0
        assert row["volume"]["axial_span_m"] > 0.08
        assert row["volume"]["max_radial_extent_m"] > 0.02
        assert set(row["digits"]) == {"1", "2", "3", "4", "5"}
        for digit, digit_row in row["digits"].items():
            assert digit_row["curled_tip_to_surface_target_m"] < digit_row["open_tip_to_surface_target_m"], (side, digit, digit_row)
            assert digit_row["improvement_m"] > 1e-6
            assert abs(digit_row["target"]["surface_clearance_m"] - SURFACE_CLEARANCE_M) < 1e-12
            assert digit_row["target"]["support_radius_m"] > 0.0
            assert len(digit_row["segments"]) == 3

    print("HM08 GRIP-VOLUME V0.6 TEST PASS", {
        "minimum_target_improvement_mm": grip["minimum_target_improvement_m"] * 1000.0,
        "mean_target_improvement_mm": grip["mean_target_improvement_m"] * 1000.0,
        "tip_surface_gap_mm_range": [value * 1000.0 for value in grip["final_tip_surface_gap_m_range"]],
        "max_curl_mm": grip["finger_curl_max_displacement_m"] * 1000.0,
        "right_target_mean_mm": [grip["choices"]["right"]["open_target_mean_m"] * 1000.0, grip["choices"]["right"]["curled_target_mean_m"] * 1000.0],
        "left_target_mean_mm": [grip["choices"]["left"]["open_target_mean_m"] * 1000.0, grip["choices"]["left"]["curled_target_mean_m"] * 1000.0],
    })


if __name__ == "__main__":
    run()
