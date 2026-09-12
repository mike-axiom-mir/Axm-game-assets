#!/usr/bin/env python3
import json
import tempfile
import unittest
from pathlib import Path

from native_kettlejack_character import ASSET_NAME, SCHEMA, write_kettlejack_package


class KettlejackCharacterTests(unittest.TestCase):
    def test_build_real_animated_game_character_package(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "kettlejack"
            package = write_kettlejack_package(root, texture_size=32)
            self.assertEqual(package["schema"], SCHEMA)
            self.assertEqual(package["asset_id"], "kettlejack")
            self.assertAlmostEqual(package["height_m"], 1.30, places=8)
            self.assertTrue(all(package["acceptance"].values()), package["acceptance"])
            self.assertEqual([row["name"] for row in package["clips"]],
                             ["idle", "run", "jump", "wrench_swing", "victory"])
            self.assertGreaterEqual(package["delivery"]["primitive_count"], 8)
            self.assertEqual(package["delivery"]["validation"]["status"], "pass")
            self.assertEqual(package["delivery"]["joints"], 23)
            self.assertTrue(package["truth"]["real_skeleton"])
            self.assertTrue(package["truth"]["real_skin_weights"])
            self.assertTrue(package["truth"]["real_animation_tracks"])
            self.assertFalse(package["truth"]["concept_pixel_faithful"])
            self.assertFalse(package["truth"]["automatic_canon"])

            gltf = root / f"{ASSET_NAME}.gltf"
            binary = root / f"{ASSET_NAME}.bin"
            manifest = root / "kettlejack-package.json"
            self.assertTrue(gltf.is_file())
            self.assertTrue(binary.is_file())
            self.assertTrue(manifest.is_file())
            document = json.loads(gltf.read_text())
            self.assertEqual(len(document["animations"]), 5)
            self.assertEqual([item["name"] for item in document["animations"]],
                             ["idle", "run", "jump", "wrench_swing", "victory"])
            self.assertGreaterEqual(len(document["materials"]), 8)
            self.assertEqual(len(document["skins"][0]["joints"]), 23)
            roles = [p["extras"]["axm"]["semantic_role"]
                     for p in document["meshes"][0]["primitives"]]
            for needle in ("patched-work-clothes", "scarf", "goggle", "hubcap",
                           "kettle-pack", "mechanical-leg", "wrench"):
                self.assertTrue(any(needle in role for role in roles), (needle, roles))
            for primitive in document["meshes"][0]["primitives"]:
                self.assertIn("JOINTS_0", primitive["attributes"])
                self.assertIn("WEIGHTS_0", primitive["attributes"])
            with self.assertRaises(FileExistsError):
                write_kettlejack_package(root, texture_size=32)


if __name__ == "__main__":
    unittest.main()
