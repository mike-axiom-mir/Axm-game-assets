#!/usr/bin/env python3
import json
from math import cos, pi, sin
from pathlib import Path
from tempfile import TemporaryDirectory

from native_animation import AnimationClip, AnimationTrack
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
    blink = MorphTarget(
        "blink",
        [(0.0, 0.0, 0.0), (0.0, 0.0, 0.0), (0.0, -0.05, 0.0), (0.0, -0.05, 0.0)],
        normal_deltas=[(0.0, 0.0, 0.0)] * 4,
    )
    half = pi * 0.25
    look = AnimationClip("look_left", [AnimationTrack(1, "rotation", [0.0, 0.5], [(0.0, 0.0, 0.0, 1.0), (0.0, sin(half / 2.0), 0.0, cos(half / 2.0))])])

    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        write_painted_metal(root / "textures", size=32, seed=99)
        result = write_character_gltf(mesh, uv, skeleton, skin, [blink], root, animations=[look])
        assert result["validation"]["status"] == "pass"
        assert result["joints"] == 2
        assert result["morph_targets"] == 1
        assert result["morph_tangent_targets"] == 1
        assert result["animations"] == 1
        document = json.loads((root / result["gltf"]).read_text())
        attributes = document["meshes"][0]["primitives"][0]["attributes"]
        assert "JOINTS_0" in attributes and "WEIGHTS_0" in attributes
        assert "TANGENT" in attributes
        assert len(document["skins"][0]["joints"]) == 2
        ibm_accessor = document["accessors"][document["skins"][0]["inverseBindMatrices"]]
        assert ibm_accessor["type"] == "MAT4" and ibm_accessor["count"] == 2
        targets = document["meshes"][0]["primitives"][0]["targets"]
        assert len(targets) == 1
        assert set(targets[0]) == {"POSITION", "NORMAL", "TANGENT"}
        tangent_accessor = document["accessors"][targets[0]["TANGENT"]]
        assert tangent_accessor["type"] == "VEC3"
        assert tangent_accessor["count"] == document["extras"]["axm"]["compiled_vertices"]
        assert document["extras"]["axm"]["morph_tangent_targets"] == 1
        assert document["meshes"][0]["extras"]["targetNames"] == ["blink"]
        assert document["nodes"][0]["skin"] == 0
        assert len(document["animations"]) == 1
        channel = document["animations"][0]["channels"][0]
        assert channel["target"] == {"node": 2, "path": "rotation"}
        input_accessor = document["accessors"][document["animations"][0]["samplers"][0]["input"]]
        assert input_accessor["type"] == "SCALAR" and input_accessor["min"] == [0.0] and input_accessor["max"] == [0.5]
        print(
            "NATIVE CHARACTER GLTF TEST PASS",
            result["joints"], "joints",
            result["morph_targets"], "morph",
            result["morph_tangent_targets"], "morph tangent target",
            result["animations"], "animation",
        )


if __name__ == "__main__":
    run()
