#!/usr/bin/env python3

from native_hm08_extremity_gear import _load_identity_body
from native_hm08_rifle_contact_pose import build_hm08_rifle_contact_pose


def run() -> None:
    body_m, _body_uv, _state = _load_identity_body()
    first_mesh, first = build_hm08_rifle_contact_pose(body_m)
    second_mesh, second = build_hm08_rifle_contact_pose(body_m)

    assert first == second
    assert first_mesh.vertices == second_mesh.vertices
    assert first_mesh.faces == second_mesh.faces
    assert first["schema"] == "axm.game-assets.hm08-rifle-contact-pose.v0.1"
    assert first["pose_id"] == "cross_chest_low_ready_v0.1"

    weapon = first["weapon"]
    assert weapon["scale"] == [1.0, 1.0, 1.0]
    assert first["truth"]["rifle_scaled_to_fake_contact"] is False
    assert first["a_pose_hand_separation_m"] > weapon["grip_socket_separation_m"] * 1.8
    assert 0.43 < weapon["grip_socket_separation_m"] < 0.47

    contact = first["contact"]
    assert contact["primary_position_error"] < 1e-8, contact
    assert contact["primary_orientation_error_deg"] < 1e-5, contact
    assert contact["support_position_error"] < 1e-6, contact
    assert contact["support_orientation_error_deg"] < 1e-4, contact

    for side in ("right", "left"):
        centroid = first["hand_centroid_contact"][side]
        assert centroid["error_m"] < 1e-6, centroid
        bones = first["bone_lengths"][side]
        assert abs(bones["upper_bind_m"] - bones["upper_posed_m"]) < 1e-8, bones
        assert abs(bones["forearm_hand_bind_m"] - bones["forearm_hand_posed_m"]) < 1e-8, bones
        chain = first["chains"][side]
        assert chain["hand_vertices"] > 1000
        assert 0.18 < chain["upper_length_m"] < 0.24
        assert 0.17 < chain["forearm_hand_length_m"] < 0.22

    skin = first["skin_proposal"]
    assert skin["validation"]["status"] == "pass"
    assert skin["arm_vertices"]["right"] > 1500
    assert skin["arm_vertices"]["left"] > 1500
    assert skin["rigid_hand_vertices"]["right"] > 1000
    assert skin["rigid_hand_vertices"]["left"] > 1000
    assert skin["root_only_vertices"] > 7000
    assert first["moved_vertices"] > 3000
    assert first["non_arm_max_displacement_m"] < 1e-10

    assert first["truth"]["two_bone_lengths_preserved"] is True
    assert first["truth"]["canonical_body_mutated"] is False
    assert first["truth"]["production_rig_claim"] is False
    assert first["truth"]["production_skinning_claim"] is False
    assert first["truth"]["automatic_ik_runtime_claim"] is False

    print("HM08 RIFLE CONTACT POSE TEST PASS", {
        "a_pose_hand_separation_m": first["a_pose_hand_separation_m"],
        "grip_socket_separation_m": weapon["grip_socket_separation_m"],
        "primary_error_mm": contact["primary_position_error"]*1000.0,
        "support_error_mm": contact["support_position_error"]*1000.0,
        "right_hand_centroid_error_mm": first["hand_centroid_contact"]["right"]["error_m"]*1000.0,
        "left_hand_centroid_error_mm": first["hand_centroid_contact"]["left"]["error_m"]*1000.0,
        "moved_vertices": first["moved_vertices"],
        "non_arm_max_displacement_m": first["non_arm_max_displacement_m"],
    })


if __name__ == "__main__":
    run()
