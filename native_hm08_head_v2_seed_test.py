#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from native_geometry import read_obj, topology_report, triangulate
from native_targets import load_target, mix_targets, validate_target

ROOT = Path("seed_data/hm08_head_v0.2")
EXPECTED = {
    "vertices": 4197,
    "faces": 4168,
    "triangles": 8336,
    "boundary_edges": 58,
    "targets": {
        "nose-width1-incr": 60,
        "l-cheek-bones-incr": 63,
        "r-cheek-bones-incr": 63,
    },
}


def sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def run() -> None:
    manifest = json.loads((ROOT / "seed-manifest.json").read_text(encoding="utf-8"))
    assert manifest["schema"] == "axm.game-assets.hm08-head-seed.v0.2"
    assert manifest["basemesh_id"] == "axm-hm08-head-v0.2"
    assert manifest["repair_lineage"]["supersedes_for_fidelity"] == "axm-hm08-head-v0.1"
    assert "visually_rejected" in manifest["repair_lineage"]["v0.1_status"]
    assert all(manifest["acceptance"].values()), manifest["acceptance"]
    assert manifest["coordinate_space"]["name"] == "raw_makehuman_hm08_obj"
    assert manifest["coordinate_space"]["engine_conversion_applied"] is False
    assert manifest["extraction"]["selection_method"] == "metadata_vertical_slab_then_largest_connected_body_surface"

    head_path = ROOT / manifest["outputs"]["head_obj"]["file"]
    map_path = ROOT / manifest["outputs"]["source_index_map"]["file"]
    assert sha256(head_path) == manifest["outputs"]["head_obj"]["sha256"]
    assert sha256(map_path) == manifest["outputs"]["source_index_map"]["sha256"]

    source_map = json.loads(map_path.read_text(encoding="utf-8"))
    assert len(source_map["compact_to_source"]) == EXPECTED["vertices"]
    assert len(source_map["source_to_compact"]) == EXPECTED["vertices"]
    for compact, source in enumerate(source_map["compact_to_source"]):
        assert source_map["source_to_compact"][str(source)] == compact

    mesh = read_obj(head_path)
    topo = topology_report(mesh)
    assert len(mesh.vertices) == EXPECTED["vertices"]
    assert len(mesh.faces) == EXPECTED["faces"]
    assert len(triangulate(mesh).faces) == EXPECTED["triangles"]
    assert topo["invalid_indices"] == 0
    assert topo["degenerate_faces"] == 0
    assert topo["nonmanifold_edges"] == 0
    assert topo["boundary_edges"] == EXPECTED["boundary_edges"]
    assert topo["boundary_edges"] < 374

    actual = manifest["extraction"]["compact_actual_bounds"]
    reference = manifest["extraction"]["metadata_reference_bounds"]
    assert actual["x"][0] < reference["x"][0]
    assert actual["x"][1] > reference["x"][1]
    assert actual["z"][1] > reference["z"][1]

    library = {}
    target_records = {record["name"]: record for record in manifest["outputs"]["targets"]}
    for stem, rows in EXPECTED["targets"].items():
        filename = f"{stem}.target"
        path = ROOT / "targets" / filename
        record = target_records[filename]
        assert sha256(path) == record["output_sha256"]
        assert record["retained_rows"] == rows
        target = load_target(path, license="CC0-source-remap")
        assert target.metadata["basemesh"] == "axm-hm08-head-v0.2"
        report = validate_target(target, vertex_count=len(mesh.vertices))
        assert report["status"] == "pass", report
        assert report["rows"] == rows
        library[stem] = target

    weights_a = {
        "nose-width1-incr": 0.35,
        "l-cheek-bones-incr": 0.22,
        "r-cheek-bones-incr": 0.22,
    }
    weights_b = {
        "r-cheek-bones-incr": 0.22,
        "l-cheek-bones-incr": 0.22,
        "nose-width1-incr": 0.35,
    }
    variant_a, state_a = mix_targets(mesh, library, weights_a, name="sentinel_hm08_face_candidate")
    variant_b, state_b = mix_targets(mesh, library, weights_b, name="sentinel_hm08_face_candidate")
    assert variant_a.vertices == variant_b.vertices
    assert state_a == state_b
    assert variant_a.faces == mesh.faces
    moved = sum(a != b for a, b in zip(mesh.vertices, variant_a.vertices))
    assert moved >= 100, moved
    assert topology_report(variant_a) == topo

    print(
        "HM08 V0.2 OFFLINE SEED PASS",
        EXPECTED["vertices"], "verts",
        EXPECTED["triangles"], "tris",
        EXPECTED["boundary_edges"], "boundary edges",
        moved, "moved vertices",
        state_a["digest"],
    )


if __name__ == "__main__":
    run()
