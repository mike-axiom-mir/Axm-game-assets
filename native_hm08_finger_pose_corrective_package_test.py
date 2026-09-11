#!/usr/bin/env python3
from tempfile import TemporaryDirectory

from native_hm08_finger_pose_corrective_package import build_hm08_finger_pose_corrective_package


def run() -> None:
    with TemporaryDirectory() as td:
        package=build_hm08_finger_pose_corrective_package(td,texture_size=64)
    assert all(package["acceptance"].values()),package["acceptance"]
    assert package["schema"]=="axm.game-assets.hm08-finger-pose-corrective-package.v0.10"
    assert package["candidate_role"]=="same_grip_pose_pose_space_knuckle_corrective_visual_proof"
    assert package["delivery"]["primitive_count"]==5
    assert package["delivery"]["material_count"]==5
    assert package["rifle"]["scale"]==[1.0,1.0,1.0]
    corrective=package["corrective"]
    assert corrective["max_vertex_correction_m"]>0.0007
    assert corrective["active_bulge_joints"]>=10
    assert corrective["nonfinger_max_delta_from_v0_7_lbs_m"]<=1e-10
    assert package["truth"]["production_corrective_claim"] is False
    print("HM08 FINGER CORRECTIVE PACKAGE TEST PASS",{
        "max_correction_m":corrective["max_vertex_correction_m"],
        "active_bulge_joints":corrective["active_bulge_joints"],
        "radial":corrective["pointwise_radial_error"],
        "delivery":package["delivery"],
    })


if __name__=="__main__":
    run()
