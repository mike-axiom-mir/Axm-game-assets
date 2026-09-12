#!/usr/bin/env python3
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from native_kettlejack_character_v2 import write_kettlejack_v2_package


class KettlejackV2Tests(unittest.TestCase):
    def test_render_rehearsal_character_builds(self):
        with TemporaryDirectory() as tmp:
            package = write_kettlejack_v2_package(Path(tmp) / "kettlejack", texture_size=32)
            self.assertEqual(package["schema"], "axm.game-assets.kettlejack-character/v0.2")
            self.assertTrue(all(package["acceptance"].values()), package["acceptance"])
            self.assertEqual(package["delivery"]["joints"], 23)
            self.assertEqual(package["delivery"]["animations"], ["idle", "run", "jump", "wrench_swing", "victory"])
            self.assertGreaterEqual(package["delivery"]["primitive_count"], 12)
            roles = " ".join(row["semantic_role"] for row in package["accessories"])
            for required in (
                "cartoon-eye", "cartoon-pupil", "messy-hair", "forehead-goggle", "orange-scarf",
                "kettle-pack", "mechanical-leg", "heavy-work-boot", "wrench-open-jaw",
            ):
                self.assertIn(required, roles)
            self.assertTrue(package["visual_rehearsal"]["render_review_required_after_build"])
            self.assertFalse(package["truth"]["visual_match_proven"])
            self.assertFalse(package["truth"]["automatic_canon"])
            root = Path(tmp) / "kettlejack"
            gltf = json.loads((root / package["delivery"]["gltf"]).read_text())
            self.assertEqual(len(gltf["animations"]), 5)
            self.assertEqual(len(gltf["skins"][0]["joints"]), 23)


if __name__ == "__main__":
    unittest.main()
