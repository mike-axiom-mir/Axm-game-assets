#!/usr/bin/env python3

from native_hm08_rifle_contact_pose_v3 import build_preferred_human_scale_rifle_contact_pose


def run() -> None:
    first_mesh, first = build_preferred_human_scale_rifle_contact_pose()
    second_mesh, second = build_preferred_human_scale_rifle_contact_pose()
    assert first == second
    assert first_mesh.vertices == second_mesh.vertices
    assert first_mesh.faces == second_mesh.faces

    assert first["schema"] == "axm.game-assets.hm08-rifle-contact-pose.v0.3"
    assert first["pose_id"] == "cross_chest_low_ready_human_scale_rifle_v0.3"
    assert first["shared_rig"]["joint_count"] == 23
    weapon = first["weapon"]
    assert weapon["design_schema"] == "axm.game-assets.sentinel-rifle-human-scale.v0.5"
    assert 0.92 <= weapon["source_length_m"] <= 1.04
    assert weapon["scale"] == [1.0,1.0,1.0]
    assert 0.27 <= weapon["grip_socket_separation_m"] <= 0.30
    assert first["a_pose_palm_contact_separation_m"] > weapon["grip_socket_separation_m"] * 2.7

    contact = first["contact"]
    assert contact["primary_position_error"] < 1e-8, contact
    assert contact["support_position_error"] < 1e-6, contact
    assert contact["primary_orientation_error_deg"] < 1e-5, contact
    assert contact["support_orientation_error_deg"] < 1e-4, contact
    for side in ("right","left"):
        pose = first["pose"][side]
        assert pose["reach_m"] <= pose["maximum_reach_m"] + 1e-9
        bones = first["bone_lengths"][side]
        assert abs(bones["upper_bind_m"] - bones["upper_posed_m"]) < 1e-8
        assert abs(bones["forearm_bind_m"] - bones["forearm_posed_m"]) < 1e-8
        assert first["hand_visual_contact"][side]["centroid_to_socket_error_m"] < 0.060

    assert first["stationary_weight_region_max_displacement_m"] < 1e-9
    assert first["head_max_displacement_m"] < 1e-9
    assert first["lower_body_max_displacement_m"] < 1e-9
    assert first["truth"]["legacy_oversized_rifle_used"] is False
    assert first["truth"]["rifle_scaled_to_fake_contact"] is False
    assert first["truth"]["runtime_rifle_scale"] == [1.0,1.0,1.0]
    assert first["truth"]["automatic_visual_promotion"] is False
    print("HM08 HUMAN-SCALE RIFLE CONTACT V0.3 PASS", {
        "weapon_length_m": weapon["source_length_m"],
        "grip_span_m": weapon["grip_socket_separation_m"],
        "primary_error_mm": contact["primary_position_error"]*1000.0,
        "support_error_mm": contact["support_position_error"]*1000.0,
        "right_visual_error_mm": first["hand_visual_contact"]["right"]["centroid_to_socket_error_m"]*1000.0,
        "left_visual_error_mm": first["hand_visual_contact"]["left"]["centroid_to_socket_error_m"]*1000.0,
    })


if __name__ == "__main__":
    run()
