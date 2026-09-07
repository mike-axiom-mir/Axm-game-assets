#!/usr/bin/env python3
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


def _span(values):
    return max(values) - min(values)


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

    # Translation changes world-anchored UV phase but must not change physical
    # scale. A one-unit-wide shell therefore keeps the same UV span after move.
    unit_box = make_box((1.0, 1.0, 1.0), name="unit")
    moved_box = translate(unit_box, (2.75, -1.25, 0.8), name="moved")
    unit_uv = box_project_world(unit_box, world_units_per_tile=0.25)
    moved_uv = box_project_world(moved_box, world_units_per_tile=0.25)
    assert validate_uv(unit_box, unit_uv)["status"] == "pass"
    assert validate_uv(moved_box, moved_uv)["status"] == "pass"
    assert abs(_span([u for u, _ in unit_uv.uvs]) - _span([u for u, _ in moved_uv.uvs])) < 1e-9
    assert abs(_span([v for _, v in unit_uv.uvs]) - _span([v for _, v in moved_uv.uvs])) < 1e-9

    # Physical scale must survive mesh-size changes instead of renormalizing
    # every mesh to 0..1. Doubling X increases relevant UV extent by 2x.
    long_box = make_box((2.0, 1.0, 1.0), name="long")
    long_uv = box_project_world(long_box, world_units_per_tile=0.25)
    assert _span([u for u, _ in long_uv.uvs]) > _span([u for u, _ in unit_uv.uvs])

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
    print("NATIVE UV TEST PASS", len(box_uv.uvs), len(world_uv.uvs), len(sphere_uv.uvs))


if __name__ == "__main__":
    run()
