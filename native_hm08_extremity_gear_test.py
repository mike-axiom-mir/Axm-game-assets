#!/usr/bin/env python3
from tempfile import TemporaryDirectory

from native_hm08_extremity_gear import build_preferred_hm08_extremity_gear, write_sentinel_extremity_materials


def run() -> None:
    a_shell, a_uv, a_soles, a_sole_uv, a = build_preferred_hm08_extremity_gear()
    b_shell, b_uv, b_soles, b_sole_uv, b = build_preferred_hm08_extremity_gear()

    assert a == b
    assert a_shell.vertices == b_shell.vertices and a_shell.faces == b_shell.faces
    assert a_uv.uvs == b_uv.uvs and a_uv.face_uvs == b_uv.face_uvs
    assert a_soles.vertices == b_soles.vertices and a_soles.faces == b_soles.faces
    assert a_sole_uv.uvs == b_sole_uv.uvs and a_sole_uv.face_uvs == b_sole_uv.face_uvs

    assert a["schema"] == "axm.game-assets.hm08-extremity-gear.v0.1"
    assert a["source_body_vertices"] == 13380
    assert a["source_body_faces"] == 13378
    assert a["glove_face_count"] > 3000, a
    assert a["boot_upper_face_count"] > 2000, a
    assert a["shell_face_count"] > 5000, a
    assert a["glove_source_area_m2"] > 0.07, a
    assert a["boot_upper_source_area_m2"] > 0.12, a
    assert abs(a["shell_offset_m"] - 0.0024) < 1e-12
    assert a["selection"]["glove_lateral_fraction"] == 0.79
    assert a["selection"]["boot_height_fraction"] == 0.10
    assert a["shell_topology"]["invalid_indices"] == 0
    assert a["shell_topology"]["degenerate_faces"] == 0
    assert a["shell_topology"]["nonmanifold_edges"] == 0
    assert a["shell_topology"]["boundary_edges"] > 0
    assert a["shell_uv_validation"]["status"] == "pass"
    assert a["sole_topology"]["invalid_indices"] == 0
    assert a["sole_topology"]["degenerate_faces"] == 0
    assert a["sole_topology"]["nonmanifold_edges"] == 0
    assert a["sole_topology"]["closed_two_manifold_candidate"] is True
    assert a["sole_uv_validation"]["status"] == "pass"
    assert set(a["sole_components"]) == {"left", "right"}
    for side in ("left", "right"):
        row = a["sole_components"][side]
        assert row["width_m"] > 0.10
        assert row["depth_m"] > 0.22
        assert 0.02 <= row["height_m"] <= 0.04
    assert a["truth"]["source_grounded"] is True
    assert a["truth"]["canonical_body_mutated"] is False
    assert a["truth"]["production_glove_claim"] is False
    assert a["truth"]["production_boot_claim"] is False

    with TemporaryDirectory() as x, TemporaryDirectory() as y:
        mx = write_sentinel_extremity_materials(x, size=64, seed=95021)
        my = write_sentinel_extremity_materials(y, size=64, seed=95021)
        assert mx["schema"] == "axm.game-assets.sentinel-extremity-materials.v0.1"
        tx = {name: row["sha256"] for name, row in mx["textile"]["maps"].items()}
        ty = {name: row["sha256"] for name, row in my["textile"]["maps"].items()}
        assert tx == ty
        assert mx["rubber"]["maps"] == my["rubber"]["maps"]
        assert mx["textile"]["renderer_hints"]["metalness"] == 0.0
        assert mx["rubber"]["metalness"] == 0.0

    print("HM08 EXTREMITY GEAR TEST PASS", {
        "glove_faces": a["glove_face_count"],
        "boot_faces": a["boot_upper_face_count"],
        "shell_faces": len(a_shell.faces),
        "sole_faces": len(a_soles.faces),
        "glove_area_m2": a["glove_source_area_m2"],
        "boot_area_m2": a["boot_upper_source_area_m2"],
    })


if __name__ == "__main__":
    run()
