#!/usr/bin/env python3

from native_hm08_rifle_contact_pose_v5 import build_preferred_finger_grip_rifle_contact_pose


def run() -> None:
    first_mesh, first = build_preferred_finger_grip_rifle_contact_pose()
    second_mesh, second = build_preferred_finger_grip_rifle_contact_pose()
    assert first == second
    assert first_mesh.vertices == second_mesh.vertices
    assert first_mesh.faces == second_mesh.faces
    assert all(first["acceptance"].values()), first["acceptance"]

    assert first["schema"] == "axm.game-assets.hm08-rifle-contact-pose.v0.5"
    assert first["pose_id"] == "cross_chest_low_ready_finger_grip_v0.5"
    assert first["shared_rig"]["joint_count"] == 53
    assert first["shared_rig"]["finger_joint_count"] == 30
    assert first["shared_rig"]["finger_rig_evidence"]["base_joint_count"] == 23
    assert first["shared_rig"]["finger_skin_evidence"]["base_skin_schema"] == "axm.game-assets.hm08-humanoid-skin.v0.2"
    assert first["finger_grip"]["open_pose_vs_v0_4_max_error_m"] < 1e-8
    assert first["weapon"]["scale"] == [1.0,1.0,1.0]
    assert float(first["contact"]["primary_position_error"]) < 1e-8
    assert float(first["contact"]["support_position_error"]) < 1e-6

    grip = first["finger_grip"]
    assert grip["curl_moved_finger_vertices"] > 200
    assert 0.003 < grip["finger_curl_max_displacement_m"] < 0.12
    assert grip["nonfinger_curl_max_displacement_m"] < 1e-8
    assert grip["head_curl_max_displacement_m"] < 1e-9
    assert grip["lower_body_curl_max_displacement_m"] < 1e-9
    for side in ("right","left"):
        choice = grip["choices"][side]
        assert choice["curled_nonthumb_mean_m"] < choice["open_nonthumb_mean_m"], choice
        assert choice["curled_thumb_m"] < choice["open_thumb_m"], choice
        assert choice["nonthumb_sign"] in (-1.0,1.0)
        assert choice["thumb_sign"] in (-1.0,1.0)
        assert choice["nonthumb_scale"] in (0.72,0.90,1.08)
        assert choice["thumb_scale"] in (0.65,0.85,1.05)
        assert grip["finger_surface"][side]["vertex_count"] > 150
        assert grip["finger_surface"][side]["centroid_to_socket_m"] < 0.09

    assert first["truth"]["v0_4_arm_pose_preserved"] is True
    assert first["truth"]["human_scale_rifle_preserved"] is True
    assert first["truth"]["source_grounded_finger_chains"] is True
    assert first["truth"]["production_grip_claim"] is False
    assert first["truth"]["automatic_visual_promotion"] is False

    print("HM08 FINGER GRIP V0.5 TEST PASS", {
        "joints": first["shared_rig"]["joint_count"],
        "open_vs_v4_um": grip["open_pose_vs_v0_4_max_error_m"] * 1e6,
        "moved_finger_vertices": grip["curl_moved_finger_vertices"],
        "max_curl_mm": grip["finger_curl_max_displacement_m"] * 1000.0,
        "right_tip_mean_mm": [grip["choices"]["right"]["open_nonthumb_mean_m"]*1000.0, grip["choices"]["right"]["curled_nonthumb_mean_m"]*1000.0],
        "left_tip_mean_mm": [grip["choices"]["left"]["open_nonthumb_mean_m"]*1000.0, grip["choices"]["left"]["curled_nonthumb_mean_m"]*1000.0],
    })


if __name__ == "__main__":
    run()
