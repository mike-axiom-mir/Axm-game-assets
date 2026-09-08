#!/usr/bin/env python3
from tempfile import TemporaryDirectory

from native_hm08_undersuit import _load_identity_body
from native_sentinel_armor import build_sentinel_armor, write_sentinel_armor_material


def run() -> None:
    body_m, _body_uv, _state = _load_identity_body()
    first_parts, first = build_sentinel_armor(body_m)
    second_parts, second = build_sentinel_armor(body_m)
    assert first == second
    assert [p.name for p in first_parts] == [p.name for p in second_parts]
    assert [p.mesh.vertices for p in first_parts] == [p.mesh.vertices for p in second_parts]
    assert [p.mesh.faces for p in first_parts] == [p.mesh.faces for p in second_parts]

    names = [p.name for p in first_parts]
    assert names == [
        "chest_primary", "sternum_core", "back_primary", "spine_core",
        "left_shoulder", "right_shoulder", "pelvis_guard", "left_shin", "right_shin",
    ], names
    assert first["schema"] == "axm.game-assets.sentinel-armor-silhouette.v0.1"
    assert 1.5 < first["source_body_height_m"] < 1.9
    assert abs(first["clearance_m"] - 0.006) < 1e-12
    assert first["surface_anchors"]["front_chest_z_m"] > first["surface_anchors"]["back_chest_z_m"]
    assert first["combined_topology"]["invalid_indices"] == 0
    assert first["combined_topology"]["degenerate_faces"] == 0
    assert first["combined_topology"]["nonmanifold_edges"] == 0
    assert first["combined_topology"]["closed_two_manifold_candidate"] is True
    for row in first["parts"]:
        assert row["topology"]["closed_two_manifold_candidate"] is True, row

    part_by_name = {p.name: p for p in first_parts}
    left_shoulder = part_by_name["left_shoulder"].mesh
    right_shoulder = part_by_name["right_shoulder"].mesh
    left_shin = part_by_name["left_shin"].mesh
    right_shin = part_by_name["right_shin"].mesh
    assert abs(min(v[0] for v in left_shoulder.vertices) + max(v[0] for v in right_shoulder.vertices)) < 1e-9
    assert abs(max(v[0] for v in left_shoulder.vertices) + min(v[0] for v in right_shoulder.vertices)) < 1e-9
    assert abs(min(v[0] for v in left_shin.vertices) + max(v[0] for v in right_shin.vertices)) < 1e-9
    assert abs(max(v[0] for v in left_shin.vertices) + min(v[0] for v in right_shin.vertices)) < 1e-9

    with TemporaryDirectory() as a, TemporaryDirectory() as b:
        ma = write_sentinel_armor_material(a, size=64, seed=111021)
        mb = write_sentinel_armor_material(b, size=64, seed=111021)
        ha = {name: row["sha256"] for name, row in ma["maps"].items()}
        hb = {name: row["sha256"] for name, row in mb["maps"].items()}
        assert ha == hb
        assert ma["kind"] == "painted_metal"
        assert ma["spec"]["wear"] == 0.16
        assert ma["spec"]["paint_rgb"] == [45, 53, 57]

    print("SENTINEL ARMOR SILHOUETTE TEST PASS", {
        "parts": names,
        "triangles": first["combined_topology"]["triangles"],
        "front_chest_z_m": first["surface_anchors"]["front_chest_z_m"],
        "back_chest_z_m": first["surface_anchors"]["back_chest_z_m"],
        "material_hashes": ha,
    })


if __name__ == "__main__":
    run()
