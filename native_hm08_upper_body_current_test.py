#!/usr/bin/env python3
from tempfile import TemporaryDirectory

from native_hm08_upper_body_current import build_current_upper_body_package


def run() -> None:
    with TemporaryDirectory() as td:
        package = build_current_upper_body_package(td, texture_size=64)
    assert all(package["acceptance"].values()), package["acceptance"]
    assert package["schema"] == "axm.game-assets.hm08-upper-body-current.v0.1"
    assert package["candidate_role"] == "continuous_human_upper_body_candidate"
    assert package["upper_seed"]["source_vertices"] == 10185
    assert package["upper_seed"]["source_faces"] == 10158
    overlap = package["head_identity_overlap"]
    assert overlap["status"] == "pass"
    assert overlap["compared_vertices"] == 4197
    assert overlap["max_error_raw"] <= 1e-12
    assert overlap["max_error_m"] <= 1e-13
    assert package["delivery"]["primitive_count"] == 9
    assert package["delivery"]["material_count"] == 9
    assert package["delivery"]["material_names"][0] == "AXM_Sentinel_UpperBody_Skin_Continuity_v0_1"
    assert package["truth"]["production_body_claim"] is False
    assert package["truth"]["production_body_skin_claim"] is False
    assert package["truth"]["high_end_character_claim"] is False
    print("HM08 CURRENT UPPER BODY PACKAGE PASS", {
        "vertices": package["upper_seed"]["source_vertices"],
        "faces": package["upper_seed"]["source_faces"],
        "head_overlap": overlap["compared_vertices"],
        "max_error_raw": overlap["max_error_raw"],
        "triangles": package["delivery"]["triangles"],
        "materials": package["delivery"]["material_count"],
    })


if __name__ == "__main__":
    run()
