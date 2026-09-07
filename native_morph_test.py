#!/usr/bin/env python3
from native_geometry import Mesh
from native_morph import MorphTarget, apply_morphs, sparse_position_deltas, validate_morph_set


def run() -> None:
    mesh = Mesh("face_patch", [(-1.0, 0.0, 0.0), (0.0, 0.0, 0.0), (1.0, 0.0, 0.0)], [(0, 1, 2)])
    smile = MorphTarget("smile", [(0.0, 0.2, 0.0), (0.0, 0.0, 0.0), (0.0, 0.2, 0.0)])
    injury = MorphTarget("injured_left", [(0.1, -0.1, 0.0), (0.0, 0.0, 0.0), (0.0, 0.0, 0.0)])
    assert validate_morph_set([smile, injury], vertex_count=3)["status"] == "pass"
    mixed = apply_morphs(mesh, [smile, injury], [0.5, 1.0])
    assert mixed.vertices[0] == (-0.9, 0.0, 0.0)
    assert mixed.vertices[2] == (1.0, 0.1, 0.0)
    assert len(sparse_position_deltas(smile)) == 2
    broken = MorphTarget("broken", [(0.0, 0.0, 0.0)])
    assert validate_morph_set([broken], vertex_count=3)["status"] == "fail"
    print("NATIVE MORPH TEST PASS", 2, "targets")


if __name__ == "__main__":
    run()
