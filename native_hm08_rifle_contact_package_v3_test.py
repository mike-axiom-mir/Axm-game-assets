#!/usr/bin/env python3
from tempfile import TemporaryDirectory

from native_hm08_rifle_contact_package_v3 import build_hm08_rifle_contact_package_v3


def run() -> None:
    with TemporaryDirectory() as td:
        package=build_hm08_rifle_contact_package_v3(td,texture_size=64)
    assert all(package["acceptance"].values()),package["acceptance"]
    assert package["schema"]=="axm.game-assets.hm08-rifle-contact-package.v0.3"
    assert package["candidate_role"]=="human_scale_shared_rig_rifle_contact_visual_proof"
    assert package["changed_variable_from_v0_2"]=="weapon_source_dimensions_only"
    rifle=package["rifle"]["dimensional_evidence"]
    assert rifle["schema"]=="axm.game-assets.sentinel-rifle-human-scale.v0.5"
    assert 0.92<=rifle["overall_length_m"]<=1.04
    assert 0.27<=rifle["grip_socket_separation_m"]<=0.30
    assert package["rifle"]["scale"]==[1.0,1.0,1.0]
    assert package["delivery"]["primitive_count"]==5
    assert package["delivery"]["material_count"]==5
    pose=package["pose"]
    assert pose["shared_rig"]["joint_count"]==23
    assert pose["contact"]["primary_position_error"]<1e-8
    assert pose["contact"]["support_position_error"]<1e-6
    assert pose["hand_visual_contact"]["right"]["centroid_to_socket_error_m"]<0.060
    assert pose["hand_visual_contact"]["left"]["centroid_to_socket_error_m"]<0.060
    assert package["truth"]["legacy_v0_2_visual_result_preserved"] is True
    assert package["truth"]["automatic_visual_promotion"] is False
    print("HM08 HUMAN-SCALE CONTACT PACKAGE V0.3 PASS",{
        "weapon_length_m":rifle["overall_length_m"],
        "grip_span_m":rifle["grip_socket_separation_m"],
        "triangles":package["delivery"]["triangles"],
        "materials":package["delivery"]["material_count"],
    })


if __name__=="__main__":
    run()
