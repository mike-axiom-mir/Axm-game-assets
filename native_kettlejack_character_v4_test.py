#!/usr/bin/env python3
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from native_kettlejack_character_v4 import write_kettlejack_v4_package


class KettlejackV4Tests(unittest.TestCase):
    def test_third_visual_repair_builds(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp)/"kettlejack"
            package=write_kettlejack_v4_package(root,texture_size=32)
            self.assertEqual(package["schema"],"axm.game-assets.kettlejack-character/v0.4")
            self.assertTrue(all(package["acceptance"].values()),package["acceptance"])
            self.assertEqual(package["delivery"]["joints"],23)
            self.assertEqual(package["delivery"]["animations"],["idle","run","jump","wrench_swing","victory"])
            roles=" ".join(row["semantic_role"] for row in package["accessories"])
            for token in ("face-eye-recessed","face-smile","pilot-cap","layered-vest-panel","rolled-sleeve","baggy-trouser","wrench-fixed-jaw","wrench-moving-jaw"):
                self.assertIn(token,roles)
            self.assertFalse(package["truth"]["visual_match_proven"])
            doc=json.loads((root/package["delivery"]["gltf"]).read_text())
            self.assertEqual(len(doc["animations"]),5)
            self.assertEqual(len(doc["skins"][0]["joints"]),23)


if __name__=="__main__":
    unittest.main()
