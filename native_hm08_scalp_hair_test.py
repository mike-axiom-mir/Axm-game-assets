#!/usr/bin/env python3
from native_hm08_scalp_hair import build_preferred_hm08_short_scalp_hair


def run() -> None:
    first_roots, first_cards, first_uv, first = build_preferred_hm08_short_scalp_hair()
    second_roots, second_cards, second_uv, second = build_preferred_hm08_short_scalp_hair()
    assert first == second
    assert first_roots == second_roots
    assert first_cards.vertices == second_cards.vertices
    assert first_cards.faces == second_cards.faces
    assert first_uv.uvs == second_uv.uvs
    assert first_uv.face_uvs == second_uv.face_uvs

    assert first["schema"] == "axm.game-assets.hm08-short-scalp-hair.v0.2"
    assert first["guide_count"] == 320
    assert first["unique_root_count"] == 320
    assert first["root_selection"]["candidate_count"] >= 320, first["root_selection"]
    selected = first["selected_region_counts"]
    assert selected["crown"] >= 70, selected
    assert selected["side"] >= 50, selected
    assert selected["back"] >= 25, selected
    assert first["root_x_range_m"][0] < 0.0 < first["root_x_range_m"][1], first["root_x_range_m"]
    assert first["root_z_span_m"] > 0.10, first["root_z_range_m"]
    assert first["min_first_outward_dot"] > 0.10, first["min_first_outward_dot"]
    assert first["hair_validation"]["status"] == "pass", first["hair_validation"]
    assert first["uv_validation"]["status"] == "pass"
    assert first["truth"]["source_grounded"] is True
    assert first["truth"]["v0_1_visual_repair"] == "tighten_temples_and_lay_guides_along_scalp_flow"
    assert first["truth"]["preferred_scalp_hair_claim"] is False

    print("HM08 SHORT SCALP HAIR V0.2 TEST PASS", {
        "candidates": first["root_selection"]["candidate_count"],
        "regions": selected,
        "flows": first["flow_counts"],
        "guides": first["guide_count"],
        "root_x": first["root_x_range_m"],
        "root_y": first["root_y_range_m"],
        "root_z": first["root_z_range_m"],
        "min_outward_dot": first["min_first_outward_dot"],
        "card_faces": first["hair_validation"]["card_faces"],
    })


if __name__ == "__main__":
    run()
