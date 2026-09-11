#!/usr/bin/env python3
from tempfile import TemporaryDirectory

from native_hm08_rifle_grip_dqs_package import build_hm08_rifle_grip_dqs_package


def run() -> None:
    with TemporaryDirectory() as td:
        package=build_hm08_rifle_grip_dqs_package(td,texture_size=64)
    assert all(package["acceptance"].values()),package["acceptance"]
    assert package["schema"]=="axm.game-assets.hm08-rifle-grip-dqs-package.v0.8"
    assert package["candidate_role"]=="same_grip_pose_finger_local_dqs_visual_proof"
    assert package["changed_variable_from_v0_7"]=="finger_influenced_vertex_deformation_algorithm_lbs_to_dqs"
    assert package["delivery"]["primitive_count"]==5
    assert package["delivery"]["material_count"]==5
    assert package["rifle"]["scale"]==[1.0,1.0,1.0]
    assert package["dqs"]["radial_preservation"]["relative_error"]<0.90
    assert package["dqs"]["nonfinger_max_delta_from_v0_7_lbs_m"]<=1e-10
    assert package["truth"]["production_deformation_claim"] is False
    print("HM08 GRIP DQS PACKAGE TEST PASS",package["dqs"]["radial_preservation"],package["delivery"])


if __name__=="__main__":
    run()
