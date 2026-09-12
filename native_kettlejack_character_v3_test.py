#!/usr/bin/env python3
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from native_kettlejack_character_v3 import write_kettlejack_v3_package


class KettlejackV3Tests(unittest.TestCase):
    def test_second_render_repair_builds(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp)/"kettlejack"
            package=write_kettlejack_v3_package(root,texture_size=32)
            self.assertEqual(package["schema"],"axm.game-assets.kettlejack-character/v0.3")
            self.assertTrue(all(package["acceptance"].values()),package["acceptance"])
            self.assertEqual(package["delivery"]["joints"],23)
            self.assertEqual(package["delivery"]["animations"],["idle","run","jump","wrench_swing","victory"])
            self.assertGreaterEqual(package["delivery"]["primitive_count"],14)
            roles=" ".join(row["semantic_role"] for row in package["accessories"])
            for token in ("face-eye","face-brow","face-nose","face-mouth","layered-vest","rolled-sleeve","baggy-trouser","wrench-fixed-jaw","wrench-moving-jaw"):
                self.assertIn(token,roles)
            self.assertFalse(package["truth"]["visual_match_proven"])
            doc=json.loads((root/package["delivery"]["gltf"]).read_text())
            self.assertEqual(len(doc["animations"]),5)
            self.assertEqual(len(doc["skins"][0]["joints"]),23)


if __name__=="__main__":
    unittest.main()
