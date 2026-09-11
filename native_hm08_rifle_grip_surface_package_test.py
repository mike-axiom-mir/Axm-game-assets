#!/usr/bin/env python3
from tempfile import TemporaryDirectory

from native_hm08_rifle_grip_surface_package import build_hm08_rifle_grip_surface_package


def run() -> None:
    with TemporaryDirectory() as td:
        package=build_hm08_rifle_grip_surface_package(td,texture_size=64)
    assert all(package["acceptance"].values()),package["acceptance"]
    assert package["schema"]=="axm.game-assets.hm08-rifle-grip-surface-package.v0.7"
    assert package["candidate_role"]=="grip_surface_source_grounded_finger_wrap_visual_proof"
    assert package["delivery"]["primitive_count"]==5
    assert package["delivery"]["material_count"]==5
    assert package["rifle"]["scale"]==[1.0,1.0,1.0]
    summary=package["pose"]["contact_summary"]
    assert summary["digits_within_penetration_budget"]==10
    assert summary["max_surface_penetration_m"]<0.0015
    assert package["truth"]["production_grip_claim"] is False
    print("HM08 GRIP SURFACE PACKAGE TEST PASS",summary,package["delivery"])


if __name__=="__main__":
    run()
