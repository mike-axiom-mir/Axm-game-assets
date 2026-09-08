#!/usr/bin/env python3
from native_hm08_brows import build_preferred_hm08_brows


def run() -> None:
    first = build_preferred_hm08_brows()
    second = build_preferred_hm08_brows()
    assert first.evidence == second.evidence
    assert first.cards.vertices == second.cards.vertices
    assert first.cards.faces == second.cards.faces
    assert first.uvmap.uvs == second.uvmap.uvs
    assert first.uvmap.face_uvs == second.uvmap.face_uvs

    evidence = first.evidence
    assert evidence["schema"] == "axm.game-assets.hm08-brows.v0.3"
    assert evidence["guide_count"] == 48
    assert evidence["guides_per_brow"] == 24
    assert evidence["unique_anchor_count"] >= 40, evidence
    assert 0.00050 <= evidence["mean_root_surface_distance_m"] <= 0.00060, evidence
    assert evidence["max_root_surface_distance_m"] <= 0.00056, evidence
    assert evidence["left_anchor_x_range"][0] > 0.0, evidence["left_anchor_x_range"]
    assert evidence["right_anchor_x_range"][1] < 0.0, evidence["right_anchor_x_range"]
    assert abs(evidence["left_anchor_x_range"][0] + evidence["right_anchor_x_range"][1]) < 0.005
    assert abs(evidence["left_anchor_x_range"][1] + evidence["right_anchor_x_range"][0]) < 0.005
    assert evidence["hair_validation"]["status"] == "pass"
    assert evidence["hair_validation"]["min_root_outward_dot"] > 0.0
    assert evidence["uv_validation"]["status"] == "pass"
    assert evidence["truth"]["preferred_geometry_route"] is True
    assert evidence["truth"]["high_end_brow_claim"] is False

    print("HM08 BROWS TEST PASS", {
        "guides": evidence["guide_count"],
        "unique_anchors": evidence["unique_anchor_count"],
        "root_distance_mm": evidence["mean_root_surface_distance_m"] * 1000.0,
        "left_x": evidence["left_anchor_x_range"],
        "right_x": evidence["right_anchor_x_range"],
        "card_faces": evidence["hair_validation"]["card_faces"],
    })


if __name__ == "__main__":
    run()
