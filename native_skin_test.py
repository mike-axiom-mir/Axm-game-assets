#!/usr/bin/env python3
from math import cos, pi, sin

from native_geometry import Mesh
from native_skin import (
    Joint,
    Skeleton,
    SkinWeights,
    flatten_matrix_column_major,
    inverse_bind_matrices,
    normalize_weights,
    skin_vertices,
    validate_skeleton,
    validate_skin_weights,
)


def run() -> None:
    bind = Skeleton([
        Joint("root"),
        Joint("arm", parent=0, translation=(0.0, 1.0, 0.0)),
    ])
    assert validate_skeleton(bind)["status"] == "pass"

    raw = SkinWeights(
        joints=[(0, 1, 0, 0), (1, 0, 0, 0), (1, 0, 0, 0)],
        weights=[(0.25, 0.75, 0.0, 0.0), (2.0, 0.0, 0.0, 0.0), (3.0, 0.0, 0.0, 0.0)],
    )
    weights = normalize_weights(raw)
    assert validate_skin_weights(weights, vertex_count=3, joint_count=2)["status"] == "pass"
    assert abs(sum(weights.weights[0]) - 1.0) < 1e-9

    mesh = Mesh("arm_strip", [(0.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 2.0, 0.0)], [(0, 1, 2)])
    rest = skin_vertices(mesh, weights, bind, bind)
    for before, after in zip(mesh.vertices, rest):
        assert all(abs(a - b) < 1e-8 for a, b in zip(before, after))

    half = pi * 0.5
    posed = Skeleton([
        Joint("root"),
        Joint("arm", parent=0, translation=(0.0, 1.0, 0.0), rotation=(0.0, 0.0, sin(half / 2.0), cos(half / 2.0))),
    ])
    moved = skin_vertices(mesh, weights, bind, posed)
    assert moved[2][0] < -0.99 and abs(moved[2][1] - 1.0) < 1e-8, moved[2]

    ibm = inverse_bind_matrices(bind)
    assert len(ibm) == 2
    assert len(flatten_matrix_column_major(ibm[0])) == 16

    cyclic = Skeleton([Joint("a", parent=1), Joint("b", parent=0)])
    assert validate_skeleton(cyclic)["status"] == "fail"
    bad = SkinWeights([(3, 0, 0, 0)] * 3, [(1.0, 0.0, 0.0, 0.0)] * 3)
    assert validate_skin_weights(bad, vertex_count=3, joint_count=2)["status"] == "fail"
    print("NATIVE SKIN TEST PASS", len(bind.joints), "joints", len(weights.weights), "weighted vertices")


if __name__ == "__main__":
    run()
