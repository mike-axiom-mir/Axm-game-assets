#!/usr/bin/env python3
from tempfile import TemporaryDirectory

from native_hm08_rifle_contact_package_v5 import CHANGED_VARIABLE, build_hm08_rifle_contact_package_v5


def run() -> None:
    with TemporaryDirectory() as first_dir, TemporaryDirectory() as second_dir:
        first = build_hm08_rifle_contact_package_v5(first_dir, texture_size=64)
        second = build_hm08_rifle_contact_package_v5(second_dir, texture_size=64)
    assert first == second
    assert all(first["acceptance"].values()), first["acceptance"]
    assert first["schema"] == "axm.game-assets.hm08-rifle-contact-package.v0.5"
    assert first["candidate_role"] == "source_grounded_finger_grip_visual_proof"
    assert first["changed_variable_from_v0_4"] == CHANGED_VARIABLE
    assert first["pose"]["schema"] == "axm.game-assets.hm08-rifle-contact-pose.v0.5"
    assert first["pose"]["shared_rig"]["joint_count"] == 53
    assert first["pose"]["shared_rig"]["finger_joint_count"] == 30
    assert first["rifle"]["scale"] == [1.0, 1.0, 1.0]
    assert 0.92 <= first["rifle"]["dimensional_evidence"]["overall_length_m"] <= 1.04
    assert first["delivery"]["primitive_count"] == 5
    assert first["delivery"]["material_count"] == 5
    assert first["delivery"]["validation"]["status"] == "pass"
    assert first["delivery"]["material_names"][0] == "Forge_FingerGrip_ContactBody_Proposal"
    grip = first["pose"]["finger_grip"]
    assert grip["minimum_fingertip_improvement_m"] > 0.0
    assert grip["mean_fingertip_improvement_m"] > grip["minimum_fingertip_improvement_m"]
    assert grip["nonfinger_curl_max_displacement_m"] < 1e-8
    assert first["truth"]["v0_4_rifle_geometry_materials_transform_preserved"] is True
    assert first["truth"]["v0_4_camera_lab_should_be_reused"] is True
    assert first["truth"]["production_grip_claim"] is False
    assert first["truth"]["automatic_visual_promotion"] is False

    print("HM08 FINGER GRIP PACKAGE V0.5 TEST PASS", {
        "asset": first["asset"],
        "triangles": first["delivery"]["triangles"],
        "materials": first["delivery"]["material_count"],
        "minimum_tip_improvement_mm": grip["minimum_fingertip_improvement_m"] * 1000.0,
        "mean_tip_improvement_mm": grip["mean_fingertip_improvement_m"] * 1000.0,
        "max_curl_mm": grip["finger_curl_max_displacement_m"] * 1000.0,
    })


if __name__ == "__main__":
    run()
