#!/usr/bin/env python3
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from native_material_signal_audit import REQUEST_SCHEMA, audit_material_request
from native_surface_families import KINDS, write_surface_family

CHANNELS = {
    "base_color": "base-color",
    "normal": "normal",
    "roughness": "roughness",
    "metallic": "metallic",
    "height": "height",
    "ao": "ambient-occlusion",
    "orm": "unassigned",
}


class NativeSurfaceFamiliesTests(unittest.TestCase):
    def test_all_donor_families_generate_and_audit_without_hold(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            for index, kind in enumerate(KINDS):
                folder = root / kind
                manifest = write_surface_family(folder, kind=kind, size=16, seed=100 + index)
                self.assertEqual(manifest["kind"], kind)
                self.assertFalse(manifest["truth"]["physically_measured"])
                self.assertEqual(set(manifest["maps"]), set(CHANNELS))
                request = {
                    "schema": REQUEST_SCHEMA,
                    "family_id": manifest["family_id"],
                    "entries": [
                        {
                            "id": map_id,
                            "channel": CHANNELS[map_id],
                            "path": record["file"],
                        }
                        for map_id, record in sorted(manifest["maps"].items())
                    ],
                }
                report = audit_material_request(request, folder)
                self.assertNotEqual(report["status"], "HOLD", (kind, report))
                rows = {row["id"]: row for row in report["entries"]}
                self.assertTrue(rows["normal"].get("signal"))
                self.assertGreater(rows["normal"]["signal"]["normal"]["mean_z"], 0.15)

    def test_generation_is_byte_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            first = write_surface_family(root / "a", kind="wood", size=24, seed=77, name="wood-proof")
            second = write_surface_family(root / "b", kind="wood", size=24, seed=77, name="wood-proof")
            self.assertEqual(first["manifest_digest"], second["manifest_digest"])
            for key in first["maps"]:
                self.assertEqual(first["maps"][key]["sha256"], second["maps"][key]["sha256"])
                self.assertEqual(
                    (root / "a" / first["maps"][key]["file"]).read_bytes(),
                    (root / "b" / second["maps"][key]["file"]).read_bytes(),
                )

    def test_material_kinds_do_not_collapse_to_same_payload(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            wood = write_surface_family(root / "wood", kind="wood", size=20, seed=9)
            cloth = write_surface_family(root / "cloth", kind="cloth", size=20, seed=9)
            self.assertNotEqual(
                wood["maps"]["base_color"]["sha256"],
                cloth["maps"]["base_color"]["sha256"],
            )
            self.assertNotEqual(
                wood["maps"]["height"]["sha256"],
                cloth["maps"]["height"]["sha256"],
            )

    def test_custom_authoring_state_is_receipted(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "custom"
            manifest = write_surface_family(
                root,
                kind="rubber",
                size=16,
                seed=3,
                base_rgb=(18, 25, 31),
                relief_strength=4.25,
                scale=1.6,
            )
            self.assertEqual(manifest["spec"]["base_rgb"], [18, 25, 31])
            self.assertEqual(manifest["spec"]["relief_strength"], 4.25)
            self.assertEqual(manifest["spec"]["scale"], 1.6)

    def test_output_is_create_only_at_directory_body_level(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "occupied"
            root.mkdir()
            (root / "existing.txt").write_text("keep me", encoding="utf-8")
            with self.assertRaises(FileExistsError):
                write_surface_family(root, kind="stone", size=16, seed=1)
            self.assertEqual((root / "existing.txt").read_text(encoding="utf-8"), "keep me")

    def test_manifest_is_not_authority(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "family"
            manifest = write_surface_family(root, kind="salvage_metal", size=16, seed=12)
            parsed = json.loads((root / "material-family.json").read_text(encoding="utf-8"))
            self.assertEqual(parsed["manifest_digest"], manifest["manifest_digest"])
            self.assertFalse(parsed["truth"]["automatic_genome_mutation"])
            self.assertFalse(parsed["truth"]["aesthetic_quality_proven"])


if __name__ == "__main__":
    unittest.main()
