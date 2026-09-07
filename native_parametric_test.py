#!/usr/bin/env python3
from native_geometry import Mesh
from native_parametric import build_variant, geometry_digest, rebuild_variant, target_channels, topology_digest
from native_targets import SparseTarget


def run() -> None:
    seed = Mesh(
        "fixed_head_fixture",
        [(-1.0, 0.0, 0.0), (1.0, 0.0, 0.0), (-1.0, 1.0, 0.0), (1.0, 1.0, 0.0), (0.0, 0.4, 0.2), (0.0, 0.7, 0.15)],
        [(0, 1, 4), (1, 3, 5, 4), (3, 2, 5), (2, 0, 4, 5)],
    )
    targets = {
        "nose_wide": SparseTarget("nose_wide", {4: (0.0, 0.0, 0.08), 5: (0.0, 0.0, 0.04)}, source="fixture/nose_wide.target", license="CC0-1.0"),
        "injured_left": SparseTarget("injured_left", {0: (0.04, -0.02, 0.01), 2: (0.03, -0.01, 0.02)}, source="fixture/injured_left.target", license="AXM fixture"),
        "older": SparseTarget("older", {4: (0.0, -0.01, -0.01), 5: (0.0, -0.015, -0.008)}, source="fixture/older.target", license="AXM fixture"),
    }

    original_topology = topology_digest(seed)
    original_geometry = geometry_digest(seed)
    variant = build_variant(
        seed,
        targets,
        {"injured_left": 0.7, "nose_wide": 0.5, "older": 0.25},
        seed_id="fixture-head-v1",
        seed_source="fixture/base.obj",
        seed_license="CC0-1.0",
        unit_meters=0.01,
        name="sentinel_variant",
    )
    assert topology_digest(variant.mesh) == original_topology
    assert geometry_digest(variant.mesh) != original_geometry
    assert variant.state["truth"]["reconstructable"] is True
    assert [entry["name"] for entry in variant.state["active_targets"]] == ["injured_left", "nose_wide", "older"]

    rebuilt = rebuild_variant(seed, targets, variant.state)
    assert rebuilt.mesh.vertices == variant.mesh.vertices
    assert rebuilt.mesh.faces == variant.mesh.faces
    assert rebuilt.state["result"]["geometry_digest"] == variant.state["result"]["geometry_digest"]

    channels = target_channels(targets, ["older", "injured_left"], vertex_count=len(seed.vertices))
    assert [channel.name for channel in channels] == ["older", "injured_left"]
    assert len(channels[0].position_deltas) == len(seed.vertices)

    tampered = dict(targets)
    tampered["nose_wide"] = SparseTarget("nose_wide", {4: (0.0, 0.0, 0.09)})
    try:
        rebuild_variant(seed, tampered, variant.state)
    except ValueError:
        pass
    else:
        raise AssertionError("changed target digest must block reconstruction")

    print("NATIVE PARAMETRIC TEST PASS", variant.state["state_digest"], variant.state["result"])


if __name__ == "__main__":
    run()
