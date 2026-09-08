#!/usr/bin/env python3
"""Retained offline truth gate for the pinned complete hm08 body seed."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from native_geometry import read_obj, topology_report
from native_targets import load_target, validate_target

SEED = Path("seed_data/hm08_full_body_v0.1")
HEAD = Path("seed_data/hm08_head_v0.2")
UPPER = Path("seed_data/hm08_upper_body_v0.1")


def _sha(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def run() -> None:
    manifest = json.loads((SEED / "seed-manifest.json").read_text(encoding="utf-8"))
    audit = json.loads((SEED / "audit-summary.json").read_text(encoding="utf-8"))
    mapping = json.loads((SEED / "source-index-map.json").read_text(encoding="utf-8"))
    head_mapping = json.loads((HEAD / "source-index-map.json").read_text(encoding="utf-8"))
    upper_mapping = json.loads((UPPER / "source-index-map.json").read_text(encoding="utf-8"))

    assert manifest["schema"] == "axm.game-assets.hm08-full-body-seed.v0.1"
    assert manifest["basemesh_id"] == "axm-hm08-full-body-v0.1"
    assert all(manifest["acceptance"].values()), manifest["acceptance"]
    assert manifest["source"]["makehuman_revision"] == "a8bc2d54ff0ac92e78ff71431b1023eda42bf482"
    assert manifest["source"]["mpfb_revision"] == "437dd513888a92399d1d3200d2e80859fae55abc"
    assert "CC0" in manifest["source"]["license_record"]
    assert "no MakeHuman application code" in manifest["source"]["license_record"]

    body_path = SEED / "body.obj"
    assert _sha(body_path) == "sha256:482022690c88cca9d4849bfa11b4166e8d95e7ffc3573bd45e34d6cebda2c0e6"
    assert _sha(SEED / "source-index-map.json") == "sha256:01ebeda91111b0b59f0dbc8fc29206fd8ad9cf98a6fd411f4d92fab50cab83de"

    mesh = read_obj(body_path)
    topology = topology_report(mesh)
    assert len(mesh.vertices) == 13380
    assert len(mesh.faces) == 13378
    assert topology["invalid_indices"] == 0, topology
    assert topology["degenerate_faces"] == 0, topology
    assert topology["nonmanifold_edges"] == 0, topology
    assert topology["boundary_edges"] == 0, topology

    assert audit == {
        "boundary_edges": 0,
        "bounds": {
            "x": [-4.9627, 4.9627],
            "y": [-8.1676, 8.4913],
            "z": [-1.0154, 3.2147],
        },
        "faces": 13378,
        "head_source_vertices": 4197,
        "upper_body_source_vertices": 10185,
        "vertices": 13380,
    }

    body_sources = set(int(value) for value in mapping["compact_to_source"])
    head_sources = set(int(value) for value in head_mapping["compact_to_source"])
    upper_sources = set(int(value) for value in upper_mapping["compact_to_source"])
    assert len(body_sources) == 13380
    assert head_sources <= body_sources
    assert upper_sources <= body_sources
    rel = manifest["relationship_to_promoted_substrates"]
    assert rel["head_source_subset"] is True
    assert rel["upper_body_source_subset"] is True
    assert rel["missing_head_source_vertices"] == []
    assert rel["missing_upper_body_source_vertices"] == []

    expected_targets = {
        "nose-width1-incr.target": "sha256:6c0d26d80ba707eb743f27be46b5968c95afe275fa0e632700f047c074d66fc7",
        "l-cheek-bones-incr.target": "sha256:ec161d64547f2dda0724ea7ea1c75de74e88e09f929be053654dd01a89f7f09f",
        "r-cheek-bones-incr.target": "sha256:35166f382eaa46cd7175085188c511571170d1cc3bc27e7b2f4d49cde20ef725",
    }
    for name, digest in expected_targets.items():
        path = SEED / "targets" / name
        assert _sha(path) == digest
        target = load_target(path, license="CC0-source-remap")
        assert target.metadata["basemesh"] == "axm-hm08-full-body-v0.1"
        report = validate_target(target, vertex_count=len(mesh.vertices))
        assert report["status"] == "pass", report
        assert report["rows"] > 0

    assert manifest["truth"]["production_body_claim"] is False
    print("HM08 FULL BODY OFFLINE SEED PASS", {
        "vertices": len(mesh.vertices),
        "faces": len(mesh.faces),
        "boundary_edges": topology["boundary_edges"],
        "head_subset": len(head_sources),
        "upper_subset": len(upper_sources),
        "targets": sorted(expected_targets),
    })


if __name__ == "__main__":
    run()
