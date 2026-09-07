#!/usr/bin/env python3
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from native_character_gltf import write_character_gltf
from native_geometry import Mesh
from native_morph import MorphTarget
from native_pbr import write_painted_metal
from native_skin import Joint, Skeleton, SkinWeights
from native_uv import box_project


def run() -> None:
    mesh = Mesh(
        "sentinel_face_fixture",
        [(-0.5, 0.0, 0.0), (0.5, 0.0, 0.0), (-0.5, 1.0, 0.0), (0.5, 1.0, 0.0)],
        [(0, 1, 3, 2)],
    )
    uv = box_project(mesh)
    skeleton = Skeleton([
        Joint("root"),
        Joint("head", parent=0, translation=(0.0, 0.5, 0.0)),
    ])
    skin = SkinWeights(
        joints=[(0, 1, 0, 0), (0, 1, 0, 0), (1, 0, 0, 0), (1, 0, 0, 0)],
        weights=[(0.8, 0.2, 0.0, 0.0), (0.8, 0.2, 0.0, 0.0), (1.0, 0.0, 0.0, 0.0), (1.0, 0.0, 0.0, 0.0)],
    )
    blink = MorphTarget("blink", [(0.0, 0.0, 0.0), (0.0, 0.0, 0.0), (0.0, -0.05, 0.0), (0.0, -0.05, 0.0)])

    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        write_painted_metal(root / "textures", size=32, seed=99)
        result = write_character_gltf(mesh, uv, skeleton, skin, [blink], root)
        assert result["validation"]["status"] == "pass"
        assert result["joints"] == 2
        assert result["morph_targets"] == 1
        document = json.loads((root / result["gltf"]).read_text())
        attributes = document["meshes"][0]["primitives"][0]["attributes"]
        assert "JOINTS_0" in attributes and "WEIGHTS_0" in attributes
        assert "TANGENT" in attributes
        assert len(document["skins"][0]["joints"]) == 2
        ibm_accessor = document["accessors"][document["skins"][0]["inverseBindMatrices"]]
        assert ibm_accessor["type"] == "MAT4" and ibm_accessor["count"] == 2
        assert len(document["meshes"][0]["primitives"][0]["targets"]) == 1
        assert document["meshes"][0]["extras"]["targetNames"] == ["blink"]
        assert document["nodes"][0]["skin"] == 0
        print("NATIVE CHARACTER GLTF TEST PASS", result["joints"], "joints", result["morph_targets"], "morph")


if __name__ == "__main__":
    run()
