#!/usr/bin/env python3
import json
import tempfile
import unittest
from pathlib import Path

from native_animation import AnimationClip, AnimationTrack
from native_geometry import make_box, translate
from native_hm08_humanoid_rig import axis_angle_quaternion
from native_skin import Joint, Skeleton
from native_skinned_multi_gltf import (
    SkinnedMaterialPrimitive,
    rigid_skin_weights,
    write_skinned_multi_gltf,
)
from native_surface_families import write_surface_family
from native_uv import box_project_world


class SkinnedMultiGltfTests(unittest.TestCase):
    def test_two_materials_shared_skin_and_animation(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            write_surface_family(root / "textures" / "cloth", kind="cloth", size=16, seed=1)
            write_surface_family(root / "textures" / "steel", kind="steel", size=16, seed=2)
            skeleton = Skeleton([
                Joint("root"),
                Joint("child", parent=0, translation=(0.0, 0.5, 0.0)),
            ])
            lower = make_box((0.5, 0.5, 0.5), name="lower")
            upper = translate(make_box((0.3, 0.3, 0.3), name="upper"), (0.0, 0.65, 0.0), name="upper")
            clip = AnimationClip("wave", [
                AnimationTrack(
                    1, "rotation", [0.0, 0.5, 1.0],
                    [
                        axis_angle_quaternion((0,0,1), 0),
                        axis_angle_quaternion((0,0,1), 30),
                        axis_angle_quaternion((0,0,1), 0),
                    ],
                )
            ])
            primitives = [
                SkinnedMaterialPrimitive(
                    lower, box_project_world(lower),
                    rigid_skin_weights(lower, 0),
                    "cloth", "textures/cloth/base_color.png", "textures/cloth/normal.png", "textures/cloth/orm.png",
                    metallic_factor=0.0, semantic_role="body",
                ),
                SkinnedMaterialPrimitive(
                    upper, box_project_world(upper),
                    rigid_skin_weights(upper, 1),
                    "steel", "textures/steel/base_color.png", "textures/steel/normal.png", "textures/steel/orm.png",
                    semantic_role="accessory",
                ),
            ]
            result = write_skinned_multi_gltf(primitives, skeleton, root, [clip], name="fixture")
            self.assertEqual(result["validation"]["status"], "pass")
            self.assertEqual(result["primitive_count"], 2)
            self.assertEqual(result["animations"], ["wave"])
            doc = json.loads((root / "fixture.gltf").read_text())
            self.assertEqual(len(doc["meshes"][0]["primitives"]), 2)
            self.assertEqual(len(doc["materials"]), 2)
            self.assertEqual(len(doc["skins"][0]["joints"]), 2)
            self.assertEqual([a["name"] for a in doc["animations"]], ["wave"])
            for primitive in doc["meshes"][0]["primitives"]:
                self.assertIn("JOINTS_0", primitive["attributes"])
                self.assertIn("WEIGHTS_0", primitive["attributes"])
                self.assertIn("TANGENT", primitive["attributes"])
            with self.assertRaises(FileExistsError):
                write_skinned_multi_gltf(primitives, skeleton, root, [clip], name="fixture")


if __name__ == "__main__":
    unittest.main()
