#!/usr/bin/env python3
from pathlib import Path
from tempfile import TemporaryDirectory

from native_geometry import make_box, write_obj
from native_pipeline import build_rigid_package
from native_uv import box_project, write_obj_uv


def run() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        no_uv = root / "input-no-uv.obj"
        mesh = make_box((0.8, 0.22, 1.1), name="sentinel_plate_route")
        write_obj(mesh, no_uv, include_normals=False)
        package = build_rigid_package(no_uv, root / "package-a", material_size=64, seed=31415)
        assert package["truth"]["blender_required"] is False
        assert package["truth"]["high_end_character_claim"] is False
        assert package["uv"]["decision"] == "box_projection_fallback"
        assert package["delivery"]["validation"]["status"] == "pass"
        assert (root / "package-a" / "package-manifest.json").exists()
        assert len(list((root / "package-a" / "receipts").glob("*.json"))) == 5

        with_uv = root / "input-with-uv.obj"
        uv = box_project(mesh)
        write_obj_uv(mesh, uv, with_uv)
        preserved = build_rigid_package(with_uv, root / "package-b", material_size=64, seed=31415)
        assert preserved["uv"]["decision"] == "preserved"
        assert preserved["delivery"]["binary_sha256"] == package["delivery"]["binary_sha256"]
        print("NATIVE PIPELINE TEST PASS", package["delivery"]["gltf"], len(package["files"]), "hashed files")


if __name__ == "__main__":
    run()
