#!/usr/bin/env python3
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from native_glb_delivery import build_verified_glb_delivery
from native_pipeline import build_rigid_package
from threejs_glb_review import ThreeJsReviewError, build_threejs_review_stage


def write_proxy(path: Path) -> None:
    path.write_text(
        """o northpole-guard-review-proxy
v -0.25 0.0 -0.15
v 0.25 0.0 -0.15
v 0.25 1.82 -0.15
v -0.25 1.82 -0.15
v -0.25 0.0 0.15
v 0.25 0.0 0.15
v 0.25 1.82 0.15
v -0.25 1.82 0.15
f 1 2 3
f 1 3 4
f 5 8 7
f 5 7 6
f 1 5 6
f 1 6 2
f 2 6 7
f 2 7 3
f 3 7 8
f 3 8 4
f 5 1 4
f 5 4 8
""",
        encoding="utf-8",
    )


def fake_three(root: Path, version: str = "0.180.0") -> None:
    (root / "build").mkdir(parents=True)
    (root / "examples/jsm/loaders").mkdir(parents=True)
    (root / "examples/jsm/controls").mkdir(parents=True)
    (root / "examples/jsm/utils").mkdir(parents=True)
    (root / "package.json").write_text(json.dumps({"name": "three", "version": version}), encoding="utf-8")
    (root / "build/three.module.js").write_text("export const REVISION='180';\n", encoding="utf-8")
    (root / "examples/jsm/loaders/GLTFLoader.js").write_text("export class GLTFLoader {}\n", encoding="utf-8")
    (root / "examples/jsm/controls/OrbitControls.js").write_text("export class OrbitControls {}\n", encoding="utf-8")
    (root / "examples/jsm/utils/BufferGeometryUtils.js").write_text("export function toTrianglesDrawMode(){}\n", encoding="utf-8")
    (root / "LICENSE").write_text("Three.js test license fixture\n", encoding="utf-8")


def build_fixture(root: Path) -> tuple[Path, Path]:
    source = root / "northpole-guard-review-proxy.obj"
    package = root / "package"
    glb = root / "northpole-guard-review-proxy.glb"
    receipt = root / "delivery-receipt.json"
    write_proxy(source)
    manifest = build_rigid_package(source, package, material_size=16, seed=7)
    delivery = build_verified_glb_delivery(
        package,
        glb,
        expected_manifest_sha256=manifest["manifest_sha256"],
    )
    receipt.write_text(json.dumps(delivery, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return glb, receipt


class ThreeJsGlbReviewTests(unittest.TestCase):
    def test_builds_offline_stage_from_exact_verified_delivery(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            glb, receipt = build_fixture(root)
            three = root / "three"
            fake_three(three)
            out = root / "review"
            result = build_threejs_review_stage(
                glb_path=glb,
                delivery_receipt_path=receipt,
                three_root=three,
                expected_three_version="0.180.0",
                output_dir=out,
            )
            self.assertEqual(result["status"], "READY_FOR_LOCAL_ENGINE_REVIEW")
            self.assertFalse(result["truth"]["browser_render_observed"])
            self.assertFalse(result["authority"]["visual_approval"])
            self.assertEqual((out / "asset.glb").read_bytes(), glb.read_bytes())
            self.assertTrue((out / "vendor/THREE-LICENSE.txt").is_file())
            self.assertTrue((out / "vendor/addons/loaders/GLTFLoader.js").is_file())
            self.assertTrue((out / "vendor/addons/utils/BufferGeometryUtils.js").is_file())
            rendered = (out / "index.html").read_text(encoding="utf-8")
            self.assertNotIn("https://", rendered)
            self.assertNotIn("http://", rendered)
            self.assertIn("ENGINE RENDERED ≠ VISUALLY APPROVED", rendered)

    def test_changed_glb_fails_before_output(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            glb, receipt = build_fixture(root)
            glb.write_bytes(glb.read_bytes() + b"changed")
            three = root / "three"
            fake_three(three)
            out = root / "review"
            with self.assertRaisesRegex(ThreeJsReviewError, "validation failed|digest does not match"):
                build_threejs_review_stage(
                    glb_path=glb,
                    delivery_receipt_path=receipt,
                    three_root=three,
                    expected_three_version="0.180.0",
                    output_dir=out,
                )
            self.assertFalse(out.exists())

    def test_widened_visual_authority_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            glb, receipt = build_fixture(root)
            data = json.loads(receipt.read_text(encoding="utf-8"))
            data["authority"]["visual_approval"] = True
            receipt.write_text(json.dumps(data), encoding="utf-8")
            three = root / "three"
            fake_three(three)
            with self.assertRaisesRegex(ThreeJsReviewError, "authority widened"):
                build_threejs_review_stage(
                    glb_path=glb,
                    delivery_receipt_path=receipt,
                    three_root=three,
                    expected_three_version="0.180.0",
                    output_dir=root / "review",
                )

    def test_three_version_mismatch_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            glb, receipt = build_fixture(root)
            three = root / "three"
            fake_three(three, version="0.179.0")
            with self.assertRaisesRegex(ThreeJsReviewError, "version mismatch"):
                build_threejs_review_stage(
                    glb_path=glb,
                    delivery_receipt_path=receipt,
                    three_root=three,
                    expected_three_version="0.180.0",
                    output_dir=root / "review",
                )


if __name__ == "__main__":
    unittest.main(verbosity=2)
