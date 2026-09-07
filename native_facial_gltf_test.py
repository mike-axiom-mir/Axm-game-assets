#!/usr/bin/env python3
import json
from math import cos, pi, sin
from pathlib import Path
from tempfile import TemporaryDirectory

from native_animation import AnimationClip, AnimationTrack
from native_facial import MorphWeightClip
from native_facial_gltf import write_facial_character_gltf
from native_geometry import Mesh
from native_morph import MorphTarget
from native_skin import Joint, Skeleton, SkinWeights
from native_skin_material import write_skin_material
from native_uv import box_project


def run() -> None:
    mesh = Mesh(
        "sentinel_facial_fixture",
        [(-0.5, 0.0, 0.0), (0.5, 0.0, 0.0), (-0.5, 1.0, 0.0), (0.5, 1.0, 0.0)],
        [(0, 1, 3, 2)],
    )
    uv = box_project(mesh)
    skeleton = Skeleton([Joint("root"), Joint("head", parent=0, translation=(0.0, 0.5, 0.0))])
    skin = SkinWeights(
        joints=[(0, 1, 0, 0), (0, 1, 0, 0), (1, 0, 0, 0), (1, 0, 0, 0)],
        weights=[(0.8, 0.2, 0.0, 0.0), (0.8, 0.2, 0.0, 0.0), (1.0, 0.0, 0.0, 0.0), (1.0, 0.0, 0.0, 0.0)],
    )
    morphs = [
        MorphTarget("blink_left", [(0.0,0.0,0.0), (0.0,0.0,0.0), (0.0,-0.05,0.0), (0.0,0.0,0.0)]),
        MorphTarget("blink_right", [(0.0,0.0,0.0), (0.0,0.0,0.0), (0.0,0.0,0.0), (0.0,-0.05,0.0)]),
        MorphTarget("cheek_corrective", [(0.0,0.0,0.0), (0.0,0.0,0.0), (0.015,0.01,0.0), (-0.015,0.01,0.0)]),
    ]
    look_angle = pi * 0.20
    look = AnimationClip("look", [
        AnimationTrack(1, "rotation", [0.0, 0.5], [(0.0,0.0,0.0,1.0), (0.0,sin(look_angle/2.0),0.0,cos(look_angle/2.0))])
    ])
    blink = MorphWeightClip(
        "blink",
        [0.0, 0.08, 0.16],
        [(0.0,0.0,0.0), (1.0,1.0,0.0), (0.0,0.0,0.0)],
    )

    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        write_skin_material(root / "textures", size=32, seed=112)
        result = write_facial_character_gltf(
            mesh,
            uv,
            skeleton,
            skin,
            morphs,
            root,
            skeletal_animations=[look],
            morph_animations=[blink],
        )
        assert result["validation"]["status"] == "pass"
        assert result["skeletal_animations"] == 1
        assert result["morph_animations"] == 1
        assert result["weight_channels"] == 1
        document = json.loads((root / result["gltf"]).read_text())
        weight_animations = [
            animation for animation in document["animations"]
            if any(channel["target"].get("path") == "weights" for channel in animation["channels"])
        ]
        assert len(weight_animations) == 1
        animation = weight_animations[0]
        assert animation["name"] == "blink"
        assert animation["channels"][0]["target"] == {"node": 0, "path": "weights"}
        sampler = animation["samplers"][0]
        input_accessor = document["accessors"][sampler["input"]]
        output_accessor = document["accessors"][sampler["output"]]
        assert input_accessor["count"] == 3 and input_accessor["min"] == [0.0] and input_accessor["max"] == [0.16]
        assert output_accessor["type"] == "SCALAR" and output_accessor["count"] == 9
        print("NATIVE FACIAL GLTF TEST PASS", result)


if __name__ == "__main__":
    run()
