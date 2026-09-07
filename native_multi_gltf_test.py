#!/usr/bin/env python3
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from native_geometry import make_box, translate
from native_multi_gltf import MaterialPrimitive, write_multi_gltf
from native_pbr import PaintedMetalSpec, write_painted_metal
from native_uv import box_project


def run() -> None:
    left = make_box((1.0, 1.0, 1.0), name="left_shell")
    right = translate(make_box((0.7, 0.8, 0.9), name="right_shell"), (1.4, 0.0, 0.0))
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        write_painted_metal(
            root / "textures" / "coat",
            size=8,
            seed=101,
            spec=PaintedMetalSpec(paint_rgb=(28, 34, 40), wear=0.12),
        )
        write_painted_metal(
            root / "textures" / "polymer",
            size=8,
            seed=202,
            spec=PaintedMetalSpec(
                paint_rgb=(18, 20, 22),
                metal_rgb=(30, 32, 34),
                paint_roughness=0.78,
                metal_roughness=0.72,
                wear=0.02,
            ),
        )
        delivery = write_multi_gltf(
            [
                MaterialPrimitive(
                    left,
                    box_project(left),
                    "CoatedMetal",
                    "textures/coat/base_color.png",
                    "textures/coat/normal.png",
                    "textures/coat/orm.png",
                ),
                MaterialPrimitive(
                    right,
                    box_project(right),
                    "DarkPolymer",
                    "textures/polymer/base_color.png",
                    "textures/polymer/normal.png",
                    "textures/polymer/orm.png",
                    metallic_factor=0.0,
                ),
            ],
            root,
            name="multi_fixture",
        )
        assert delivery["validation"]["status"] == "pass", delivery
        assert delivery["primitive_count"] == 2
        assert delivery["material_count"] == 2
        assert delivery["triangles"] == 24
        assert delivery["material_names"] == ["CoatedMetal", "DarkPolymer"]
        document = json.loads((root / "multi_fixture.gltf").read_text())
        assert len(document["meshes"][0]["primitives"]) == 2
        assert [primitive["material"] for primitive in document["meshes"][0]["primitives"]] == [0, 1]
        assert document["materials"][1]["pbrMetallicRoughness"]["metallicFactor"] == 0.0
        print("NATIVE MULTI GLTF TEST PASS", delivery)


if __name__ == "__main__":
    run()
