#!/usr/bin/env python3
from tempfile import TemporaryDirectory

from native_hm08_rifle_contact_package_v5 import build_hm08_rifle_contact_package_v5


def run() -> None:
    with TemporaryDirectory() as td:
        package = build_hm08_rifle_contact_package_v5(td, texture_size=64)
    assert all(package["acceptance"].values()), package["acceptance"]
    assert package["schema"] == "axm.game-assets.hm08-rifle-contact-package.v0.5"
    assert package["candidate_role"] == "articulated_finger_shared_rig_rifle_contact_visual_proof"
    assert package["changed_variable_from_v0_4"] == "source_grounded_finger_articulation_only"
    grip = package["grip"]
    assert grip["schema"] == "axm.game-assets.hm08-finger-grip-pose.v0.2"
    assert grip["finger_rig"]["total_joint_count"] == 53
    assert grip["finger_skin"]["validation"]["status"] == "pass"
    assert grip["finger_changed_vertices"] > 200
    assert grip["nonfinger_max_delta_from_v0_4_m"] < 1e-8
    assert grip["contact"]["primary_position_error"] < 1e-8
    assert grip["contact"]["support_position_error"] < 1e-6
    assert package["rifle"]["scale"] == [1.0,1.0,1.0]
    dims = package["rifle"]["dimensional_evidence"]
    assert 0.92 <= dims["overall_length_m"] <= 1.04
    assert package["delivery"]["primitive_count"] == 5
    assert package["delivery"]["material_count"] == 5
    assert package["delivery"]["material_names"][0] == "Forge_ArticulatedGrip_ContactBody"
    assert package["truth"]["arm_pose_changed"] is False
    assert package["truth"]["weapon_changed"] is False
    assert package["truth"]["production_grip_claim"] is False
    assert package["truth"]["trigger_finger_claim"] is False
    assert package["truth"]["automatic_visual_promotion"] is False
    print("HM08 ARTICULATED CONTACT PACKAGE V0.5 PASS", {
        "joints": grip["finger_rig"]["total_joint_count"],
        "finger_vertices": grip["finger_skin"]["overridden_finger_vertices"],
        "finger_changed_vertices": grip["finger_changed_vertices"],
        "weapon_length_m": dims["overall_length_m"],
        "triangles": package["delivery"]["triangles"],
    })


if __name__ == "__main__":
    run()
