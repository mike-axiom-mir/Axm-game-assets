#!/usr/bin/env python3

from native_hm08_boot_structure import build_hm08_boot_rubber_structure
from native_hm08_extremity_gear import _load_identity_body, build_hm08_extremity_gear


def run() -> None:
    body_m, body_uv, _state = _load_identity_body()
    _shell, _shell_uv, soles, _sole_uv, gear = build_hm08_extremity_gear(body_m, body_uv)
    first, first_uv, first_evidence = build_hm08_boot_rubber_structure(body_m, soles)
    second, second_uv, second_evidence = build_hm08_boot_rubber_structure(body_m, soles)

    assert first_evidence == second_evidence
    assert first.vertices == second.vertices and first.faces == second.faces
    assert first_uv.uvs == second_uv.uvs and first_uv.face_uvs == second_uv.face_uvs

    evidence = first_evidence
    assert evidence["schema"] == "axm.game-assets.hm08-boot-rubber-structure.v0.1"
    assert evidence["toe_component_count"] == 2
    assert evidence["rubber_component_count"] == 3
    assert evidence["topology"]["invalid_indices"] == 0
    assert evidence["topology"]["degenerate_faces"] == 0
    assert evidence["topology"]["nonmanifold_edges"] == 0
    assert evidence["uv_validation"]["status"] == "pass"
    assert evidence["truth"]["body_grounded"] is True
    assert evidence["truth"]["canonical_body_mutated"] is False
    assert evidence["truth"]["source_boot_upper_replaced"] is False
    assert evidence["truth"]["production_boot_claim"] is False

    for side in ("left", "right"):
        row = evidence["side_evidence"][side]
        assert row["toe_width_m"] > row["source_width_m"]
        assert 0.09 <= row["toe_depth_m"] <= 0.125
        assert 0.058 <= row["toe_height_m"] <= 0.076
        assert 0.004 <= row["toe_chamfer_m"] <= 0.010
        assert row["toe_front_margin_m"] >= 0.01

    assert gear["sole_topology"]["closed_two_manifold_candidate"] is True
    assert len(first.faces) > len(soles.faces)
    print("HM08 BOOT RUBBER STRUCTURE TEST PASS", {
        "faces": len(first.faces),
        "source_sole_faces": len(soles.faces),
        "left": evidence["side_evidence"]["left"],
        "right": evidence["side_evidence"]["right"],
    })


if __name__ == "__main__":
    run()
