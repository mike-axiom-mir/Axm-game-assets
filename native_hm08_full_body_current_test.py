#!/usr/bin/env python3
from tempfile import TemporaryDirectory

from native_hm08_full_body_current import build_current_full_body_package


def run() -> None:
    with TemporaryDirectory() as td:
        package = build_current_full_body_package(td, texture_size=64)
    assert all(package["acceptance"].values()), package["acceptance"]
    assert package["schema"] == "axm.game-assets.hm08-full-body-current.v0.1"
    assert package["candidate_role"] == "complete_human_body_candidate"
    assert package["full_seed"]["source_vertices"] == 13380
    assert package["full_seed"]["source_faces"] == 13378
    head = package["head_identity_overlap"]
    upper = package["upper_body_identity_overlap"]
    assert head["status"] == "pass" and head["compared_vertices"] == 4197 and head["max_error_raw"] <= 1e-12
    assert upper["status"] == "pass" and upper["compared_vertices"] == 10185 and upper["max_error_raw"] <= 1e-12
    assert package["delivery"]["primitive_count"] == 9
    assert package["delivery"]["material_count"] == 9
    assert package["delivery"]["material_names"][0] == "AXM_Sentinel_FullBody_Skin_Continuity_v0_1"
    assert package["truth"]["production_body_claim"] is False
    assert package["truth"]["rigged_character_claim"] is False
    assert package["truth"]["high_end_character_claim"] is False
    print("HM08 CURRENT FULL BODY PACKAGE PASS", {
        "vertices": package["full_seed"]["source_vertices"],
        "faces": package["full_seed"]["source_faces"],
        "head_overlap": head["compared_vertices"],
        "upper_overlap": upper["compared_vertices"],
        "triangles": package["delivery"]["triangles"],
        "materials": package["delivery"]["material_count"],
    })


if __name__ == "__main__":
    run()
