#!/usr/bin/env python3
from native_hm08_scalp_underlay import build_preferred_hm08_scalp_underlay, write_scalp_underlay_material
from tempfile import TemporaryDirectory


def run() -> None:
    first_mesh, first_uv, first = build_preferred_hm08_scalp_underlay()
    second_mesh, second_uv, second = build_preferred_hm08_scalp_underlay()
    assert first == second
    assert first_mesh.vertices == second_mesh.vertices
    assert first_mesh.faces == second_mesh.faces
    assert first_uv.uvs == second_uv.uvs
    assert first_uv.face_uvs == second_uv.face_uvs

    assert first["schema"] == "axm.game-assets.hm08-scalp-underlay.v0.1"
    assert first["selected_face_count"] > 100, first
    assert first["selected_vertex_count"] > 100, first
    assert first["selected_face_count"] < first["source_face_count"], first
    assert abs(first["offset_m"] - 0.00035) < 1e-12
    assert first["y_range_m"][0] > first["eye_y_m"] - 0.020, first["y_range_m"]
    assert max(abs(first["x_range_m"][0]), abs(first["x_range_m"][1])) < first["half_width_m"] * 0.95
    assert first["uv_validation"]["status"] == "pass"
    assert first["truth"]["source_grounded"] is True
    assert first["truth"]["source_uv_preserved"] is True
    assert first["truth"]["preferred_claim"] is False

    with TemporaryDirectory() as td:
        material_a = write_scalp_underlay_material(td, size=64, seed=82081)
        hashes_a = {name: row["sha256"] for name, row in material_a["maps"].items()}
    with TemporaryDirectory() as td:
        material_b = write_scalp_underlay_material(td, size=64, seed=82081)
        hashes_b = {name: row["sha256"] for name, row in material_b["maps"].items()}
    assert hashes_a == hashes_b
    assert material_a["pbr"]["metallic_factor"] == 0.0

    print("HM08 SCALP UNDERLAY TEST PASS", {
        "faces": first["selected_face_count"],
        "vertices": first["selected_vertex_count"],
        "offset_mm": first["offset_m"] * 1000.0,
        "x_range": first["x_range_m"],
        "y_range": first["y_range_m"],
        "z_range": first["z_range_m"],
        "material_hashes": hashes_a,
    })


if __name__ == "__main__":
    run()
