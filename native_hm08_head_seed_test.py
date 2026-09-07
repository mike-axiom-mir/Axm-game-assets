#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from native_geometry import read_obj, topology_report, triangulate
from native_targets import load_target, mix_targets, validate_target

ROOT = Path("seed_data/hm08_head_v0.1")
EXPECTED = {
    "vertices": 3423,
    "faces": 3246,
    "triangles": 6492,
    "boundary_edges": 374,
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
    assert manifest["schema"] == "axm.game-assets.hm08-head-seed.v0.1"
    assert manifest["basemesh_id"] == "axm-hm08-head-v0.1"
    assert all(manifest["acceptance"].values()), manifest["acceptance"]
    assert manifest["coordinate_space"]["name"] == "raw_makehuman_hm08_obj"
    assert manifest["coordinate_space"]["engine_conversion_applied"] is False

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
    assert topo["closed_two_manifold_candidate"] is False

    library = {}
    manifest_targets = {record["name"]: record for record in manifest["outputs"]["targets"]}
    for stem, rows in EXPECTED["targets"].items():
        filename = f"{stem}.target"
        path = ROOT / "targets" / filename
        record = manifest_targets[filename]
        assert sha256(path) == record["output_sha256"]
        assert record["retained_rows"] == rows
        target = load_target(path, license="CC0-source-remap")
        assert target.metadata["basemesh"] == "axm-hm08-head-v0.1"
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
        "nose-width1-incr": 0.35,
        "l-cheek-bones-incr": 0.22,
    }
    variant_a, state_a = mix_targets(mesh, library, weights_a, name="sentinel_hm08_face_candidate")
    variant_b, state_b = mix_targets(mesh, library, weights_b, name="sentinel_hm08_face_candidate")
    assert variant_a.vertices == variant_b.vertices
    assert variant_a.faces == mesh.faces
    assert state_a == state_b
    assert state_a["digest"] == state_b["digest"]
    assert len(variant_a.vertices) == EXPECTED["vertices"]
    assert len(variant_a.faces) == EXPECTED["faces"]
    moved = sum(a != b for a, b in zip(mesh.vertices, variant_a.vertices))
    assert moved >= 100, moved
    assert topology_report(variant_a) == topo

    print(
        "HM08 OFFLINE SEED PASS",
        EXPECTED["vertices"], "verts",
        EXPECTED["triangles"], "tris",
        moved, "moved vertices",
        state_a["digest"],
    )


if __name__ == "__main__":
    run()
