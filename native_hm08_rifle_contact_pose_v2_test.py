#!/usr/bin/env python3

from native_hm08_rifle_contact_pose_v2 import build_preferred_shared_rig_rifle_contact_pose


def run() -> None:
    first_mesh, first = build_preferred_shared_rig_rifle_contact_pose()
    second_mesh, second = build_preferred_shared_rig_rifle_contact_pose()
    assert first == second
    assert first_mesh.vertices == second_mesh.vertices
    assert first_mesh.faces == second_mesh.faces

    assert first["schema"] == "axm.game-assets.hm08-rifle-contact-pose.v0.2"
    assert first["pose_id"] == "cross_chest_low_ready_shared_rig_v0.2"
    assert first["shared_rig"]["schema"] == "axm.game-assets.hm08-humanoid-rig.v0.1"
    assert first["shared_rig"]["joint_count"] == 23
    assert first["shared_rig"]["skeleton_evidence"]["skeleton_validation"]["status"] == "pass"
    assert first["shared_rig"]["skin_evidence"]["validation"]["status"] == "pass"
    assert first["shared_rig"]["skin_evidence"]["max_influences"] <= 4

    weapon = first["weapon"]
    assert weapon["scale"] == [1.0,1.0,1.0]
    assert 0.43 < weapon["grip_socket_separation_m"] < 0.47
    assert first["a_pose_palm_contact_separation_m"] > weapon["grip_socket_separation_m"] * 1.8

    contact = first["contact"]
    assert contact["primary_position_error"] < 1e-8, contact
    assert contact["primary_orientation_error_deg"] < 1e-5, contact
    assert contact["support_position_error"] < 1e-6, contact
    assert contact["support_orientation_error_deg"] < 1e-4, contact

    for side in ("right","left"):
        arm = first["arms"][side]
        assert arm["hand_vertices"] > 1000
        assert 0.16 <= arm["upper_length_m"] <= 0.30
        assert 0.16 <= arm["forearm_hand_length_m"] <= 0.32
        pose = first["pose"][side]
        assert pose["reach_m"] <= pose["maximum_reach_m"] + 1e-9
        bones = first["bone_lengths"][side]
        assert abs(bones["upper_bind_m"] - bones["upper_posed_m"]) < 1e-8, bones
        assert abs(bones["forearm_bind_m"] - bones["forearm_posed_m"]) < 1e-8, bones
        visual = first["hand_visual_contact"][side]
        assert visual["centroid_to_socket_error_m"] < 0.060, visual

    assert first["moved_vertices"] > 1000
    assert first["stationary_weight_region_max_displacement_m"] < 1e-9
    assert first["head_max_displacement_m"] < 1e-9
    assert first["lower_body_max_displacement_m"] < 1e-9
    assert first["truth"]["uses_shared_full_body_rig"] is True
    assert first["truth"]["temporary_arm_only_skeleton_used"] is False
    assert first["truth"]["character_hand_sockets_explicit"] is True
    assert first["truth"]["rifle_scaled_to_fake_contact"] is False
    assert first["truth"]["canonical_body_mutated"] is False
    assert first["truth"]["production_rig_claim"] is False
    assert first["truth"]["runtime_ik_claim"] is False

    print("HM08 SHARED-RIG RIFLE CONTACT V0.2 PASS", {
        "primary_error_mm": contact["primary_position_error"]*1000.0,
        "support_error_mm": contact["support_position_error"]*1000.0,
        "right_visual_hand_error_mm": first["hand_visual_contact"]["right"]["centroid_to_socket_error_m"]*1000.0,
        "left_visual_hand_error_mm": first["hand_visual_contact"]["left"]["centroid_to_socket_error_m"]*1000.0,
        "moved_vertices": first["moved_vertices"],
        "joint_count": first["shared_rig"]["joint_count"],
    })


if __name__ == "__main__":
    run()
