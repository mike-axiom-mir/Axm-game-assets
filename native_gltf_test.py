#!/usr/bin/env python3
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from native_geometry import make_box
from native_gltf import write_gltf
from native_pbr import write_painted_metal
from native_uv import box_project


def build(root: Path):
    mesh = make_box((0.8, 0.22, 1.1), name="sentinel_armor_plate")
    uv = box_project(mesh)
    write_painted_metal(root / "textures", size=64, seed=2718)
    return write_gltf(mesh, uv, root)


def run() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        a = build(root / "a")
        b = build(root / "b")
        assert a["validation"]["status"] == "pass"
        assert a["triangles"] == 12
        assert a["compiled_vertices"] == 36
        assert a["gltf_sha256"] == b["gltf_sha256"]
        assert a["binary_sha256"] == b["binary_sha256"]
        doc = json.loads((root / "a" / "sentinel_armor_plate.gltf").read_text())
        assert doc["asset"]["version"] == "2.0"
        assert doc["materials"][0]["pbrMetallicRoughness"]["metallicRoughnessTexture"]["index"] == 1
        assert (root / "a" / "textures" / "base_color.png").exists()
        assert (root / "a" / "textures" / "orm.png").exists()
        print("NATIVE GLTF TEST PASS", a["triangles"], "triangles", a["compiled_vertices"], "compiled vertices")


if __name__ == "__main__":
    run()
