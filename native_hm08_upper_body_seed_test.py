#!/usr/bin/env python3
"""Retained offline truth gate for the pinned hm08 upper-body seed."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from native_geometry import read_obj, topology_report
from native_targets import load_target, validate_target

SEED = Path("seed_data/hm08_upper_body_v0.1")
HEAD = Path("seed_data/hm08_head_v0.2")


def _sha(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def run() -> None:
    manifest = json.loads((SEED / "seed-manifest.json").read_text(encoding="utf-8"))
    audit = json.loads((SEED / "audit-summary.json").read_text(encoding="utf-8"))
    mapping = json.loads((SEED / "source-index-map.json").read_text(encoding="utf-8"))
    head_mapping = json.loads((HEAD / "source-index-map.json").read_text(encoding="utf-8"))

    assert manifest["schema"] == "axm.game-assets.hm08-upper-body-seed.v0.1"
    assert manifest["basemesh_id"] == "axm-hm08-upper-body-v0.1"
    assert all(manifest["acceptance"].values()), manifest["acceptance"]
    assert manifest["source"]["makehuman_revision"] == "a8bc2d54ff0ac92e78ff71431b1023eda42bf482"
    assert manifest["source"]["mpfb_revision"] == "437dd513888a92399d1d3200d2e80859fae55abc"
    assert "CC0" in manifest["source"]["license_record"]
    assert "no MakeHuman application code" in manifest["source"]["license_record"]

    mesh_path = SEED / "upper_body.obj"
    assert _sha(mesh_path) == "sha256:1f1495a1683b8fefc08396f201fe5ea1ae8a585282d14206ef6271d03bbcebe9"
    assert _sha(SEED / "source-index-map.json") == "sha256:0e65d5c568d14afe198f6acd2b5295e02a5e92c865ed7ee7cede07e7a408e901"

    mesh = read_obj(mesh_path)
    topology = topology_report(mesh)
    assert len(mesh.vertices) == 10185
    assert len(mesh.faces) == 10158
    assert topology["invalid_indices"] == 0, topology
    assert topology["degenerate_faces"] == 0, topology
    assert topology["nonmanifold_edges"] == 0, topology
    assert topology["boundary_edges"] == 52, topology

    assert audit == {
        "boundary_edges": 52,
        "faces": 10158,
        "head_source_vertices": 4197,
        "vertical_slab_y": [-0.3662, 8.4913],
        "vertices": 10185,
    }

    upper_sources = set(int(value) for value in mapping["compact_to_source"])
    head_sources = set(int(value) for value in head_mapping["compact_to_source"])
    assert len(upper_sources) == 10185
    assert len(head_sources) == 4197
    assert head_sources <= upper_sources
    assert manifest["relationship_to_head_seed"]["head_source_subset"] is True
    assert manifest["relationship_to_head_seed"]["missing_head_source_vertices"] == []

    expected_targets = {
        "nose-width1-incr.target": "sha256:e9be845de302526fdb532578588e7d2a5ff56d2226430a3701cf3221b36384c6",
        "l-cheek-bones-incr.target": "sha256:ad1dd45c0bf48910499471a1aa6abc61d66123af8baebc8ec20830ca8bc0852d",
        "r-cheek-bones-incr.target": "sha256:5cc90b296b4a3110b2f583d408f3b2569f9af9fb87a6db980b2deccbe5c8daf3",
    }
    for name, digest in expected_targets.items():
        path = SEED / "targets" / name
        assert _sha(path) == digest
        target = load_target(path, license="CC0-source-remap")
        assert target.metadata["basemesh"] == "axm-hm08-upper-body-v0.1"
        report = validate_target(target, vertex_count=len(mesh.vertices))
        assert report["status"] == "pass", report
        assert report["rows"] > 0

    assert manifest["truth"]["production_body_claim"] is False
    print("HM08 UPPER BODY OFFLINE SEED PASS", {
        "vertices": len(mesh.vertices),
        "faces": len(mesh.faces),
        "boundary_edges": topology["boundary_edges"],
        "head_subset": len(head_sources),
        "targets": sorted(expected_targets),
    })


if __name__ == "__main__":
    run()
