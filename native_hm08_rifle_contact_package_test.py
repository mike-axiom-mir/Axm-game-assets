#!/usr/bin/env python3
from tempfile import TemporaryDirectory

from native_hm08_rifle_contact_package import build_hm08_rifle_contact_package


def run() -> None:
    with TemporaryDirectory() as td:
        package = build_hm08_rifle_contact_package(td, texture_size=64)
    assert all(package["acceptance"].values()), package["acceptance"]
    assert package["schema"] == "axm.game-assets.hm08-rifle-contact-package.v0.2"
    assert package["candidate_role"] == "shared_rig_two_hand_rifle_contact_visual_proof"
    assert package["changed_variable"] == "shared_humanoid_rig_contact_pose_plus_real_rifle"
    assert package["rifle"]["scale"] == [1.0,1.0,1.0]
    assert package["delivery"]["primitive_count"] == 5
    assert package["delivery"]["material_count"] == 5
    assert package["delivery"]["material_names"][0] == "Forge_SharedRig_ContactBody_Proposal"
    assert set(package["rifle"]["semantic_groups"]) == {"coated","polymer","steel","accessory"}
    pose = package["pose"]
    assert pose["truth"]["uses_shared_full_body_rig"] is True
    assert pose["truth"]["temporary_arm_only_skeleton_used"] is False
    assert pose["truth"]["character_hand_sockets_explicit"] is True
    assert pose["shared_rig"]["joint_count"] == 23
    assert pose["contact"]["support_position_error"] < 1e-6
    assert pose["contact"]["support_orientation_error_deg"] < 1e-4
    assert pose["hand_visual_contact"]["right"]["centroid_to_socket_error_m"] < 0.060
    assert pose["hand_visual_contact"]["left"]["centroid_to_socket_error_m"] < 0.060
    assert pose["stationary_weight_region_max_displacement_m"] < 1e-9
    assert pose["head_max_displacement_m"] < 1e-9
    assert pose["lower_body_max_displacement_m"] < 1e-9
    assert package["truth"]["production_rig_claim"] is False
    assert package["truth"]["rigid_armor_contact_claim"] is False
    assert package["truth"]["temporary_arm_only_skeleton_used"] is False
    assert package["truth"]["automatic_visual_promotion"] is False
    print("HM08 SHARED-RIG RIFLE CONTACT PACKAGE TEST PASS", {
        "triangles": package["delivery"]["triangles"],
        "materials": package["delivery"]["material_count"],
        "support_error_mm": pose["contact"]["support_position_error"]*1000.0,
        "right_visual_hand_error_mm": pose["hand_visual_contact"]["right"]["centroid_to_socket_error_m"]*1000.0,
        "left_visual_hand_error_mm": pose["hand_visual_contact"]["left"]["centroid_to_socket_error_m"]*1000.0,
        "rifle_scale": package["rifle"]["scale"],
        "joint_count": pose["shared_rig"]["joint_count"],
    })


if __name__ == "__main__":
    run()
