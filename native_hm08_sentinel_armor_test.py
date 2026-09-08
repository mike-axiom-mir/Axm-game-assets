#!/usr/bin/env python3
from tempfile import TemporaryDirectory

from native_hm08_undersuit import _load_identity_body
from native_hm08_sentinel_armor import build_sentinel_rigid_armor, write_sentinel_armor_materials


def run() -> None:
    body_m, _body_uv, _state = _load_identity_body()
    first_primary, first_primary_uv, first_accent, first_accent_uv, first = build_sentinel_rigid_armor(body_m)
    second_primary, second_primary_uv, second_accent, second_accent_uv, second = build_sentinel_rigid_armor(body_m)

    assert first == second
    assert first_primary.vertices == second_primary.vertices
    assert first_primary.faces == second_primary.faces
    assert first_primary_uv.uvs == second_primary_uv.uvs
    assert first_primary_uv.face_uvs == second_primary_uv.face_uvs
    assert first_accent.vertices == second_accent.vertices
    assert first_accent.faces == second_accent.faces
    assert first_accent_uv.uvs == second_accent_uv.uvs
    assert first_accent_uv.face_uvs == second_accent_uv.face_uvs

    assert first["schema"] == "axm.game-assets.hm08-sentinel-rigid-armor.v0.2"
    assert first["design_revision"] == "segmented_anatomical_v0.2"
    assert 1.4 <= first["body_bounds_m"]["height"] <= 2.2
    assert first["primary_component_count"] >= 20, first
    assert first["accent_component_count"] >= 12, first

    for name in (
        "left_pectoral", "right_pectoral", "sternum_core",
        "left_collar", "right_collar",
        "abdomen_leaf_1", "abdomen_leaf_2", "abdomen_leaf_3",
        "left_scapula", "right_scapula", "back_spine_shell",
        "left_pauldron", "right_pauldron",
        "left_forearm_guard", "right_forearm_guard",
        "left_thigh_plate", "right_thigh_plate",
        "left_knee_plate", "right_knee_plate",
        "left_shin_plate", "right_shin_plate",
    ):
        assert name in first["primary_components"], (name, first["primary_components"])

    assert "chest_core" not in first["primary_components"]
    assert "back_core" not in first["primary_components"]

    for name in (
        "sternum_rail",
        "left_pectoral_rail", "right_pectoral_rail",
        "left_collar_rail", "right_collar_rail",
        "abdomen_rail_1", "abdomen_rail_2", "abdomen_rail_3",
        "back_rail",
        "left_forearm_rail", "right_forearm_rail",
        "left_shin_rail", "right_shin_rail",
    ):
        assert name in first["accent_components"], (name, first["accent_components"])

    assert first["primary_topology"]["invalid_indices"] == 0
    assert first["primary_topology"]["degenerate_faces"] == 0
    assert first["primary_topology"]["nonmanifold_edges"] == 0
    assert first["accent_topology"]["invalid_indices"] == 0
    assert first["accent_topology"]["degenerate_faces"] == 0
    assert first["accent_topology"]["nonmanifold_edges"] == 0
    assert first["primary_uv_validation"]["status"] == "pass"
    assert first["accent_uv_validation"]["status"] == "pass"
    assert first["chest_detail_level"] == 3
    assert "biomech_ports" in first["chest_detail_features"]
    assert first["silhouette_intent"]["torso"].startswith("split pectorals")
    assert first["truth"]["body_grounded"] is True
    assert first["truth"]["production_armor_claim"] is False
    assert first["truth"]["copied_character_design_claim"] is False

    with TemporaryDirectory() as a, TemporaryDirectory() as b:
        ma = write_sentinel_armor_materials(a, size=64, seed=93021)
        mb = write_sentinel_armor_materials(b, size=64, seed=93021)
        assert ma["schema"] == "axm.game-assets.sentinel-armor-material-set.v0.2"
        for material_name in ("primary", "accent"):
            ah = {name: row["sha256"] for name, row in ma[material_name]["maps"].items()}
            bh = {name: row["sha256"] for name, row in mb[material_name]["maps"].items()}
            assert ah == bh
        assert ma["primary"]["spec"]["paint_rgb"] == [39, 48, 54]
        assert ma["accent"]["spec"]["paint_rgb"] == [18, 23, 27]
        assert ma["primary"]["spec"]["wear"] < 0.10
        assert ma["accent"]["spec"]["wear"] < 0.15

    print("HM08 SENTINEL ARMOR V0.2 TEST PASS", {
        "primary_components": first["primary_component_count"],
        "accent_components": first["accent_component_count"],
        "primary_faces": len(first_primary.faces),
        "accent_faces": len(first_accent.faces),
        "chest_front_z": first["anchors_m"]["chest_front_z"],
        "chest_back_z": first["anchors_m"]["chest_back_z"],
        "design_revision": first["design_revision"],
    })


if __name__ == "__main__":
    run()
