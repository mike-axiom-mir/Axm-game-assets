#!/usr/bin/env python3
from native_geometry import Mesh
from native_targets import (
    SparseTarget,
    apply_target,
    compose_targets,
    mix_targets,
    parse_target_text,
    target_digest,
    to_morph_target,
    validate_target,
)

MAKEHUMAN_CC0_SAMPLE = """# This is a target file for MakeHuman
# This asset was explicitly released as CC0 in september 2020.
# basemesh hm08
97 -.001 0 0
104 -.003 0 0
105 -.009 -.001 0
6881 .001 0 0
6888 .003 0 0
6889 .009 -.001 0
"""


def run() -> None:
    target = parse_target_text(
        MAKEHUMAN_CC0_SAMPLE,
        name="nose-width1-incr",
        source="MakeHuman CC0 target sample",
        license="CC0-1.0",
    )
    assert target.metadata["basemesh"] == "hm08"
    assert target.metadata["rows"] == 6
    assert validate_target(target, vertex_count=7000)["status"] == "pass"

    vertices = [(0.0, 0.0, 0.0)] * 7000
    mesh = Mesh("hm08-fixture", vertices, [(0, 1, 2)])
    changed = apply_target(mesh, target, 1.0)
    assert changed.vertices[97][0] == -0.001
    assert changed.vertices[6881][0] == 0.001
    assert changed.faces == mesh.faces

    depth = SparseTarget("nose-depth", {97: (0.0, 0.0, 0.02), 6881: (0.0, 0.0, 0.02)})
    mixed_a, state_a = mix_targets(mesh, {target.name: target, depth.name: depth}, {target.name: 0.5, depth.name: 0.25})
    mixed_b, state_b = mix_targets(mesh, {depth.name: depth, target.name: target}, {depth.name: 0.25, target.name: 0.5})
    assert mixed_a.vertices == mixed_b.vertices
    assert state_a["digest"] == state_b["digest"]
    assert mixed_a.vertices[97] == (-0.0005, 0.0, 0.005)

    combined = compose_targets("sentinel-nose", [(target, 0.5), (depth, 0.25)])
    composed_mesh = apply_target(mesh, combined, 1.0)
    assert composed_mesh.vertices == mixed_a.vertices
    assert len(combined.metadata["lineage"]) == 2

    morph = to_morph_target(target, vertex_count=7000)
    assert len(morph.position_deltas) == 7000
    assert morph.position_deltas[105] == (-0.009, -0.001, 0.0)

    bad = SparseTarget("bad", {7001: (1.0, 0.0, 0.0)})
    assert validate_target(bad, vertex_count=7000)["status"] == "fail"
    try:
        parse_target_text("4 0 0 1\n4 0 0 2\n", name="duplicate")
    except ValueError:
        pass
    else:
        raise AssertionError("duplicate target rows must fail")

    assert target_digest(target).startswith("sha256:")
    print("NATIVE TARGET TEST PASS", target.metadata["rows"], "sparse rows", state_a["digest"])


if __name__ == "__main__":
    run()
