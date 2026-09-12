#!/usr/bin/env python3
from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from native_geometry import make_box, write_obj
from native_glb_delivery import build_verified_glb_delivery
from native_pipeline import build_rigid_package
from native_shared_glb_pack import (
    SharedGlbPackError,
    pack_glb_to_shared,
    pack_shared_collection,
    read_glb,
)


def build_real_forge_glb(root: Path, *, seed: int = 41) -> Path:
    source = root / "source.obj"
    write_obj(make_box((1.2, 0.7, 0.9), name="donor-pack-proof"), source, include_normals=False)
    package = build_rigid_package(source, root / "package", material_size=16, seed=seed)
    output = root / "delivery.glb"
    receipt = build_verified_glb_delivery(
        root / "package",
        output,
        expected_manifest_sha256=package["manifest_sha256"],
    )
    assert receipt["delivery"]["validation"]["status"] == "pass"
    return output


class NativeSharedGlbPackTests(unittest.TestCase):
    def test_real_forge_glb_round_trips_into_shared_collection(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            glb = build_real_forge_glb(root)
            second = root / "delivery-copy.glb"
            shutil.copyfile(glb, second)
            result = pack_shared_collection(
                {"first": glb, "second": second},
                root / "shared",
            )
            self.assertEqual(result["status"], "PASS")
            self.assertEqual(set(result["assets"]), {"first", "second"})
            self.assertEqual(result["shared_texture_count"], 7)
            first_doc = json.loads((root / "shared/assets/first/first.gltf").read_text())
            second_doc = json.loads((root / "shared/assets/second/second.gltf").read_text())
            self.assertEqual(
                [image["uri"].split("/")[-1] for image in first_doc["images"]],
                [image["uri"].split("/")[-1] for image in second_doc["images"]],
            )
            self.assertTrue(all(
                report["lossless_views_verified"]
                for report in result["assets"].values()
            ))

    def test_low_level_pack_preserves_semantic_sections(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            glb = build_real_forge_glb(root)
            _, original, _ = read_glb(glb)
            report = pack_glb_to_shared(
                glb,
                root / "out/asset.gltf",
                root / "out/textures",
            )
            written = json.loads((root / "out/asset.gltf").read_text())
            for key in report["semantic_sections_preserved"]:
                self.assertEqual(written.get(key), original.get(key), key)
            self.assertFalse(report["truth_boundary"]["automatic_canon"])

    def test_shared_texture_corruption_is_not_overwritten(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            glb = build_real_forge_glb(root)
            textures = root / "textures"
            first = pack_glb_to_shared(glb, root / "a/a.gltf", textures)
            target = textures / first["delivery"]["shared_images"][0]["shared_path"]
            target.write_bytes(b"corrupt")
            with self.assertRaises(SharedGlbPackError):
                pack_glb_to_shared(glb, root / "b/b.gltf", textures)
            self.assertEqual(target.read_bytes(), b"corrupt")

    def test_destination_is_create_only(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            glb = build_real_forge_glb(root)
            textures = root / "textures"
            pack_glb_to_shared(glb, root / "a/asset.gltf", textures)
            with self.assertRaises(SharedGlbPackError):
                pack_glb_to_shared(glb, root / "a/asset.gltf", textures)

    def test_truncated_glb_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            glb = build_real_forge_glb(root)
            bad = root / "bad.glb"
            bad.write_bytes(glb.read_bytes()[:-11])
            with self.assertRaises(SharedGlbPackError):
                read_glb(bad)


if __name__ == "__main__":
    unittest.main()
