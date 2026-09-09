#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory

from native_hm08_face_motion import TARGET_ORDER
from native_hm08_face_motion_gltf import write_hm08_face_motion_gltf


def run() -> None:
    with TemporaryDirectory() as first, TemporaryDirectory() as second:
        result_a = write_hm08_face_motion_gltf(first, texture_size=64)
        result_b = write_hm08_face_motion_gltf(second, texture_size=64)

        assert all(result_a["acceptance"].values()), result_a["acceptance"]
        assert result_a["validation"]["status"] == "pass", result_a["validation"]
        assert result_a["vertices"] == 4197
        assert result_a["faces"] == 4168
        assert result_a["morph_targets"] == list(TARGET_ORDER)
        assert result_a["motion_clips"] == ["blink_test", "smile_test", "jaw_open_test"]
        assert result_a["gltf_sha256"] == result_b["gltf_sha256"]
        assert result_a["binary_sha256"] == result_b["binary_sha256"]
        assert result_a["manifest_sha256"] == result_b["manifest_sha256"]
        assert result_a["truth"]["engine_motion_observer"] is True
        assert result_a["truth"]["visual_quality_claim"] is False

        root = Path(first)
        document = json.loads((root / result_a["gltf"]).read_text(encoding="utf-8"))
        assert document["asset"]["version"] == "2.0"
        assert document["meshes"][0]["extras"]["targetNames"] == list(TARGET_ORDER)
        assert len(document["meshes"][0]["weights"]) == len(TARGET_ORDER)
        assert document["materials"][0]["pbrMetallicRoughness"]["metallicFactor"] == 0.0
        assert document["extras"]["axm"]["schema"] == "axm.game-assets.hm08-face-motion-gltf.v0.1"
        assert document["extras"]["axm"]["motion_target_order"] == list(TARGET_ORDER)

        weight_animations = [
            animation
            for animation in document["animations"]
            if any(channel["target"].get("path") == "weights" for channel in animation["channels"])
        ]
        assert [animation["name"] for animation in weight_animations] == [
            "blink_test",
            "smile_test",
            "jaw_open_test",
        ]
        assert all(animation["channels"][0]["target"] == {"node": 0, "path": "weights"} for animation in weight_animations)

        # Delivery geometry is meters, not the source decimeter space.
        position_accessor = document["accessors"][0]
        assert max(abs(value) for value in position_accessor["min"] + position_accessor["max"]) < 1.0

        for texture in ("base_color.png", "normal.png", "orm.png"):
            assert (root / "textures" / texture).exists()

        print(
            "HM08 FACE MOTION GLTF PASS",
            {
                "gltf": result_a["gltf_sha256"],
                "binary": result_a["binary_sha256"],
                "morph_targets": result_a["morph_targets"],
                "motion_clips": result_a["motion_clips"],
            },
        )


if __name__ == "__main__":
    run()
