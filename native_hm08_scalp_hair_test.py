#!/usr/bin/env python3
from native_hm08_scalp_hair import build_preferred_hm08_short_scalp_hair


def run() -> None:
    first_rooted, first_cards, first_uv, first = build_preferred_hm08_short_scalp_hair()
    second_rooted, second_cards, second_uv, second = build_preferred_hm08_short_scalp_hair()
    assert first == second
    assert first_rooted.root_indices == second_rooted.root_indices
    assert first_rooted.system.guides == second_rooted.system.guides
    assert first_cards.vertices == second_cards.vertices
    assert first_cards.faces == second_cards.faces
    assert first_uv.uvs == second_uv.uvs
    assert first_uv.face_uvs == second_uv.face_uvs

    assert first["schema"] == "axm.game-assets.hm08-short-scalp-hair.v0.1"
    assert first["guide_count"] == 256
    assert first["unique_root_count"] == 256
    assert first["root_selection"]["candidate_count"] >= 256, first["root_selection"]
    assert first["selected_crown_roots"] >= 40, first
    assert first["selected_back_side_roots"] >= 40, first
    assert first["root_x_range_m"][0] < 0.0 < first["root_x_range_m"][1], first["root_x_range_m"]
    assert first["root_z_span_m"] > 0.06, first["root_z_range_m"]
    assert first["root_y_range_m"][0] >= first["root_selection"]["back_side_y_m"] - 1e-9
    assert first["hair_validation"]["status"] == "pass", first["hair_validation"]
    assert first["hair_validation"]["min_root_outward_dot"] > 0.0
    assert first["uv_validation"]["status"] == "pass"
    assert first["truth"]["source_grounded"] is True
    assert first["truth"]["preferred_scalp_hair_claim"] is False

    print("HM08 SHORT SCALP HAIR TEST PASS", {
        "candidates": first["root_selection"]["candidate_count"],
        "guides": first["guide_count"],
        "crown": first["selected_crown_roots"],
        "back_side": first["selected_back_side_roots"],
        "root_x": first["root_x_range_m"],
        "root_y": first["root_y_range_m"],
        "root_z": first["root_z_range_m"],
        "card_faces": first["hair_validation"]["card_faces"],
    })


if __name__ == "__main__":
    run()
