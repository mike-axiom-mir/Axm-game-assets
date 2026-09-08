#!/usr/bin/env python3
from tempfile import TemporaryDirectory

from native_hm08_armor import build_sentinel_armor, write_sentinel_armor_materials
from native_hm08_undersuit import _load_identity_body


def run() -> None:
    body, _uv, _state = _load_identity_body()
    first_groups, first_uvs, first = build_sentinel_armor(body)
    second_groups, second_uvs, second = build_sentinel_armor(body)
    assert first == second
    assert list(first_groups) == ["torso", "shoulders", "forearms", "shins"]
    for name in first_groups:
        assert first_groups[name].vertices == second_groups[name].vertices
        assert first_groups[name].faces == second_groups[name].faces
        assert first_uvs[name].uvs == second_uvs[name].uvs
        assert first_uvs[name].face_uvs == second_uvs[name].face_uvs
        assert first["group_topology"][name]["closed_two_manifold_candidate"] is True
        assert first["group_uv"][name]["status"] == "pass"
        assert len(first_groups[name].faces) > 0

    assert first["schema"] == "axm.game-assets.hm08-sentinel-armor.v0.1"
    assert first["torso_anchor"]["front_center"][2] > first["torso_anchor"]["source_bounds_max"][2]
    assert first["torso_anchor"]["back_center"][2] < first["torso_anchor"]["source_bounds_min"][2]
    assert first["torso_anchor"]["abdomen_plate_count"] == 3
    assert first["shoulder_centers"]["left"][0] < 0.0 < first["shoulder_centers"]["right"][0]
    assert abs(abs(first["shoulder_centers"]["left"][0]) - abs(first["shoulder_centers"]["right"][0])) < 0.02
    for side in ("left", "right"):
        assert first["forearm_anchors"][side]["axis_length_m"] > 0.10
        assert first["shin_anchors"][side]["axis_length_m"] > 0.20
    assert first["truth"]["canonical_body_mutated"] is False
    assert first["truth"]["production_fit_claim"] is False
    assert first["truth"]["deformation_clearance_claim"] is False

    with TemporaryDirectory() as a, TemporaryDirectory() as b:
        first_materials = write_sentinel_armor_materials(a, size=64, seed=101021)
        second_materials = write_sentinel_armor_materials(b, size=64, seed=101021)
        for family in ("primary", "secondary"):
            first_hashes = {name: row["sha256"] for name, row in first_materials[family]["maps"].items()}
            second_hashes = {name: row["sha256"] for name, row in second_materials[family]["maps"].items()}
            assert first_hashes == second_hashes
            assert first_materials[family]["kind"] == "painted_metal"
            assert first_materials[family]["truth"]["deterministic"] is True

    print("HM08 SENTINEL ARMOR TEST PASS", {
        "groups": {name: {"vertices": len(mesh.vertices), "faces": len(mesh.faces)} for name, mesh in first_groups.items()},
        "torso_anchor": first["torso_anchor"],
        "forearm_axes": {side: first["forearm_anchors"][side]["axis_length_m"] for side in ("left", "right")},
        "shin_axes": {side: first["shin_anchors"][side]["axis_length_m"] for side in ("left", "right")},
    })


if __name__ == "__main__":
    run()
