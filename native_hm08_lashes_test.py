#!/usr/bin/env python3
from native_hm08_lashes import build_preferred_hm08_upper_lashes


def run() -> None:
    first = build_preferred_hm08_upper_lashes()
    second = build_preferred_hm08_upper_lashes()
    assert first.evidence == second.evidence
    assert first.cards.vertices == second.cards.vertices
    assert first.cards.faces == second.cards.faces
    assert first.uvmap.uvs == second.uvmap.uvs
    assert first.uvmap.face_uvs == second.uvmap.face_uvs

    evidence = first.evidence
    assert evidence["schema"] == "axm.game-assets.hm08-upper-lashes.v0.2"
    assert evidence["guide_count"] == 48
    assert evidence["guides_per_eye"] == 24
    assert 0.00018 <= evidence["mean_root_surface_distance_m"] <= 0.00026, evidence
    assert evidence["max_root_surface_distance_m"] <= 0.00025, evidence
    assert 0.75 < evidence["min_root_eye_radius_ratio"] < 1.7, evidence
    assert 0.85 < evidence["max_root_eye_radius_ratio"] < 1.9, evidence
    assert evidence["left_root_x_range"][0] > 0.0, evidence
    assert evidence["right_root_x_range"][1] < 0.0, evidence
    assert abs(evidence["left_root_x_range"][0] + evidence["right_root_x_range"][1]) < 0.004
    assert abs(evidence["left_root_x_range"][1] + evidence["right_root_x_range"][0]) < 0.004
    assert evidence["hair_validation"]["status"] == "pass", evidence["hair_validation"]
    assert evidence["hair_validation"]["min_root_outward_dot"] > 0.0
    assert evidence["uv_validation"]["status"] == "pass"
    assert evidence["truth"]["source_grounded"] is True
    assert evidence["truth"]["upper_lashes_only"] is True
    assert evidence["truth"]["preferred_lash_claim"] is False
    assert evidence["truth"]["v0_1_visual_repair"] == "lower_root_curve_and_forward_bias"

    print("HM08 UPPER LASH TEST PASS", {
        "guides": evidence["guide_count"],
        "root_distance_mm": evidence["mean_root_surface_distance_m"] * 1000.0,
        "eye_radius_ratio": [evidence["min_root_eye_radius_ratio"], evidence["max_root_eye_radius_ratio"]],
        "left_x": evidence["left_root_x_range"],
        "right_x": evidence["right_root_x_range"],
        "card_faces": evidence["hair_validation"]["card_faces"],
    })


if __name__ == "__main__":
    run()
