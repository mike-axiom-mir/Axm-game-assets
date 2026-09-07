#!/usr/bin/env python3
from pathlib import Path
from tempfile import TemporaryDirectory

from native_geometry import make_box, make_uv_sphere
from native_uv import box_project, read_obj_uv, spherical_project, validate_uv, write_obj_uv


def run() -> None:
    box = make_box((2.0, 3.0, 4.0), name="armor_block")
    box_uv = box_project(box)
    assert validate_uv(box, box_uv)["status"] == "pass"
    assert len(box_uv.uvs) == sum(len(face) for face in box.faces)

    sphere = make_uv_sphere(1.0, segments=16, rings=8)
    sphere_uv = spherical_project(sphere)
    assert validate_uv(sphere, sphere_uv)["status"] == "pass"

    with TemporaryDirectory() as tmp:
        path = Path(tmp) / "box.obj"
        write_obj_uv(box, box_uv, path, material="AXM_Test")
        restored, restored_uv = read_obj_uv(path)
        assert len(restored.vertices) == len(box.vertices)
        assert len(restored.faces) == len(box.faces)
        assert validate_uv(restored, restored_uv)["status"] == "pass"
    print("NATIVE UV TEST PASS", len(box_uv.uvs), len(sphere_uv.uvs))


if __name__ == "__main__":
    run()
