#!/usr/bin/env python3
from tempfile import TemporaryDirectory

from native_hm08_undersuit import build_preferred_hm08_undersuit, write_sentinel_undersuit_material


def run() -> None:
    first_mesh, first_uv, first = build_preferred_hm08_undersuit()
    second_mesh, second_uv, second = build_preferred_hm08_undersuit()
    assert first == second
    assert first_mesh.vertices == second_mesh.vertices
    assert first_mesh.faces == second_mesh.faces
    assert first_uv.uvs == second_uv.uvs
    assert first_uv.face_uvs == second_uv.face_uvs

    assert first["schema"] == "axm.game-assets.hm08-undersuit.v0.1"
    assert first["source_body_vertices"] == 13380
    assert first["source_body_faces"] == 13378
    assert first["selected_face_count"] > 3000, first
    assert first["selected_vertex_count"] > 3000, first
    assert first["surface_coverage_fraction"] >= first["minimum_surface_coverage"], first
    assert first["surface_coverage_fraction"] > 0.70, first
    assert first["surface_coverage_fraction"] < 0.90, first
    assert first["selected_source_surface_area_m2"] < first["source_surface_area_m2"]
    assert abs(first["offset_m"] - 0.0022) < 1e-12
    assert first["bounds_m"]["y"][1] <= first["cuts"]["collar_y_m"] + 0.01
    assert first["bounds_m"]["y"][0] >= first["cuts"]["ankle_y_m"] - 0.01
    assert max(abs(first["bounds_m"]["x"][0]), abs(first["bounds_m"]["x"][1])) <= first["cuts"]["wrist_abs_x_m"] + 0.01
    assert first["topology"]["invalid_indices"] == 0
    assert first["topology"]["degenerate_faces"] == 0
    assert first["topology"]["nonmanifold_edges"] == 0
    assert first["topology"]["boundary_edges"] > 0
    assert first["uv_validation"]["status"] == "pass"
    assert first["truth"]["source_grounded"] is True
    assert first["truth"]["production_tailoring_claim"] is False

    with TemporaryDirectory() as a, TemporaryDirectory() as b:
        first_material = write_sentinel_undersuit_material(a, size=64, seed=91021)
        second_material = write_sentinel_undersuit_material(b, size=64, seed=91021)
        first_hashes = {name: row["sha256"] for name, row in first_material["maps"].items()}
        second_hashes = {name: row["sha256"] for name, row in second_material["maps"].items()}
        assert first_hashes == second_hashes
        assert first_material["renderer_hints"]["metalness"] == 0.0
        assert first_material["spec"]["base_rgb"] == [25, 31, 34]
        assert first_material["spec"]["thickness_hint_mm"] == 1.4

    print("HM08 UNDERSUIT TEST PASS", {
        "vertices": len(first_mesh.vertices),
        "faces": len(first_mesh.faces),
        "surface_coverage_fraction": first["surface_coverage_fraction"],
        "boundary_edges": first["topology"]["boundary_edges"],
        "offset_mm": first["offset_m"] * 1000.0,
        "bounds_m": first["bounds_m"],
        "material_hashes": first_hashes,
    })


if __name__ == "__main__":
    run()
