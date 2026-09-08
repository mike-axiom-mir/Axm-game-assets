#!/usr/bin/env python3

from native_hm08_rifle_contact_pose_v4 import build_preferred_segment_skin_rifle_contact_pose


def run() -> None:
    first_mesh,first=build_preferred_segment_skin_rifle_contact_pose()
    second_mesh,second=build_preferred_segment_skin_rifle_contact_pose()
    assert first==second
    assert first_mesh.vertices==second_mesh.vertices
    assert first_mesh.faces==second_mesh.faces
    assert first["schema"]=="axm.game-assets.hm08-rifle-contact-pose.v0.4"
    assert first["pose_id"]=="cross_chest_low_ready_segment_skin_v0.4"
    assert first["changed_variable_from_v0_3"]=="arm_skin_weights_only"
    assert first["shared_rig"]["joint_count"]==23
    assert first["shared_rig"]["skin_evidence"]["schema"]=="axm.game-assets.hm08-humanoid-skin.v0.2"
    assert first["shared_rig"]["skin_evidence"]["validation"]["status"]=="pass"
    assert first["weapon"]["design_schema"]=="axm.game-assets.sentinel-rifle-human-scale.v0.5"
    assert first["weapon"]["scale"]==[1.0,1.0,1.0]
    assert first["contact"]["primary_position_error"]<1e-8
    assert first["contact"]["support_position_error"]<1e-6
    for side in ("right","left"):
        assert first["hand_visual_contact"][side]["centroid_to_socket_error_m"]<0.060
    assert first["head_max_displacement_m"]<1e-9
    assert first["lower_body_max_displacement_m"]<1e-9
    assert first["truth"]["joint_pose_preserved_from_v0_3"] is True
    assert first["truth"]["segment_skin_v0_2_used"] is True
    assert first["truth"]["finger_chain_claim"] is False
    assert first["truth"]["automatic_visual_promotion"] is False
    print("HM08 SEGMENT-SKIN RIFLE CONTACT V0.4 PASS",{
        "right_visual_error_mm":first["hand_visual_contact"]["right"]["centroid_to_socket_error_m"]*1000.0,
        "left_visual_error_mm":first["hand_visual_contact"]["left"]["centroid_to_socket_error_m"]*1000.0,
        "v0_3_right_visual_error_mm":first["v0_3_hand_visual_contact"]["right"]["centroid_to_socket_error_m"]*1000.0,
        "v0_3_left_visual_error_mm":first["v0_3_hand_visual_contact"]["left"]["centroid_to_socket_error_m"]*1000.0,
        "moved_vertices":first["moved_vertices"],
    })


if __name__=="__main__":
    run()
