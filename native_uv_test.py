#!/usr/bin/env python3
from math import hypot
from pathlib import Path
from tempfile import TemporaryDirectory

from native_geometry import make_box, make_uv_sphere, translate
from native_uv import (
    box_project,
    box_project_world,
    read_obj_uv,
    spherical_project,
    validate_uv,
    write_obj_uv,
)


def _face_uv_edge_lengths(uvmap):
    """Return per-face UV edge lengths in retained corner order.

    World-anchored projection is allowed to change absolute UV phase under
    translation, and negative-facing planes may mirror an axis. Physical scale
    is therefore an edge-length invariant, not a global min/max UV invariant.
    """
    result = []
    for uvface in uvmap.face_uvs:
        lengths = []
        for index in range(len(uvface)):
            a = uvmap.uvs[uvface[index]]
            b = uvmap.uvs[uvface[(index + 1) % len(uvface)]]
            lengths.append(hypot(b[0] - a[0], b[1] - a[1]))
        result.append(tuple(lengths))
    return result


def run() -> None:
    box = make_box((2.0, 3.0, 4.0), name="armor_block")
    box_uv = box_project(box)
    assert validate_uv(box, box_uv)["status"] == "pass"
    assert len(box_uv.uvs) == sum(len(face) for face in box.faces)

    world_uv = box_project_world(box, world_units_per_tile=0.5)
    assert validate_uv(box, world_uv)["status"] == "pass"
    assert world_uv.method == "box_projection_world:0.5"
    assert max(abs(u) for u, _ in world_uv.uvs) > 1.0
    assert max(abs(v) for _, v in world_uv.uvs) > 1.0

    # Translation changes world-anchored UV phase, and mirrored negative faces
    # can move global min/max values asymmetrically. It must not change the UV
    # length assigned to any corresponding geometric edge.
    unit_box = make_box((1.0, 1.0, 1.0), name="unit")
    moved_box = translate(unit_box, (2.75, -1.25, 0.8), name="moved")
    unit_uv = box_project_world(unit_box, world_units_per_tile=0.25)
    moved_uv = box_project_world(moved_box, world_units_per_tile=0.25)
    assert validate_uv(unit_box, unit_uv)["status"] == "pass"
    assert validate_uv(moved_box, moved_uv)["status"] == "pass"
    unit_edges = _face_uv_edge_lengths(unit_uv)
    moved_edges = _face_uv_edge_lengths(moved_uv)
    assert len(unit_edges) == len(moved_edges)
    for before_face, after_face in zip(unit_edges, moved_edges):
        assert len(before_face) == len(after_face)
        for before, after in zip(before_face, after_face):
            assert abs(before - after) < 1e-9, (before_face, after_face)

    # Physical scale must survive mesh-size changes instead of renormalizing
    # every mesh to 0..1. make_box face 0 is a Y-normal face, so its first edge
    # projects the X dimension into UV U. Doubling X must therefore double that
    # exact edge's UV length while the world-units-per-tile value stays fixed.
    long_box = make_box((2.0, 1.0, 1.0), name="long")
    long_uv = box_project_world(long_box, world_units_per_tile=0.25)
    assert validate_uv(long_box, long_uv)["status"] == "pass"
    long_edges = _face_uv_edge_lengths(long_uv)
    assert abs(unit_edges[0][0] - 4.0) < 1e-9, unit_edges[0]
    assert abs(long_edges[0][0] - 8.0) < 1e-9, long_edges[0]
    assert abs(long_edges[0][0] / unit_edges[0][0] - 2.0) < 1e-9

    sphere = make_uv_sphere(1.0, segments=16, rings=8)
    sphere_uv = spherical_project(sphere)
    assert validate_uv(sphere, sphere_uv)["status"] == "pass"

    with TemporaryDirectory() as tmp:
        path = Path(tmp) / "box.obj"
        write_obj_uv(box, world_uv, path, material="AXM_Test")
        restored, restored_uv = read_obj_uv(path)
        assert len(restored.vertices) == len(box.vertices)
        assert len(restored.faces) == len(box.faces)
        assert validate_uv(restored, restored_uv)["status"] == "pass"
    print(
        "NATIVE UV TEST PASS",
        len(box_uv.uvs),
        len(world_uv.uvs),
        len(sphere_uv.uvs),
        "translation edge scale preserved",
        unit_edges[0][0],
        "->",
        long_edges[0][0],
    )


if __name__ == "__main__":
    run()
