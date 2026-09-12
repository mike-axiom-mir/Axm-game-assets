#!/usr/bin/env python3
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from native_kettlejack_character_v5 import write_kettlejack_v5_package


class KettlejackV5Tests(unittest.TestCase):
    def test_recovered_visual_repair_builds(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp)/"kettlejack"
            package=write_kettlejack_v5_package(root,texture_size=32)
            self.assertEqual(package["schema"],"axm.game-assets.kettlejack-character/v0.5")
            self.assertTrue(all(package["acceptance"].values()),package["acceptance"])
            self.assertTrue(package["recovery"]["v0_4_failure_retained"])
            self.assertEqual(package["delivery"]["joints"],23)
            self.assertEqual(package["delivery"]["animations"],["idle","run","jump","wrench_swing","victory"])
            self.assertFalse(package["truth"]["visual_match_proven"])
            doc=json.loads((root/package["delivery"]["gltf"]).read_text())
            self.assertEqual(len(doc["animations"]),5)
            self.assertEqual(len(doc["skins"][0]["joints"]),23)
            self.assertTrue((root/"kettlejack-v5-package.json").exists())
            self.assertFalse((root/"kettlejack-v4-package.json").exists())


if __name__=="__main__":
    unittest.main()
