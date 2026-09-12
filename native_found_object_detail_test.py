#!/usr/bin/env python3
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from native_found_object_detail import (
    build_kettle,
    build_lantern,
    build_mug,
    build_stool,
    build_tied_cargo,
    build_winch,
)
from native_geometry import topology_report
from native_preview import write_preview
from native_uv import box_project_world, validate_uv


class NativeFoundObjectDetailTests(unittest.TestCase):
    def assert_cluster_valid(self, cluster) -> None:
        self.assertGreater(len(cluster.parts), 1)
        self.assertEqual(cluster.receipt["schema"], "axm.game-assets.found-object-detail/v0.1")
        self.assertFalse(cluster.receipt["truth_boundary"]["automatic_detail_placement"])
        self.assertFalse(cluster.receipt["truth_boundary"]["automatic_canon"])
        self.assertEqual(cluster.receipt["provenance"]["donor"]["commit"], "a5cc708457b7e8f33e794fdac648ae65d15a0fb4")
        for part in cluster.parts:
            report = topology_report(part.mesh)
            self.assertTrue(report["closed_two_manifold_candidate"], (part.part_id, report))
            self.assertEqual(report["invalid_indices"], 0)
            self.assertEqual(report["degenerate_faces"], 0)
            self.assertEqual(validate_uv(part.mesh, box_project_world(part.mesh, world_units_per_tile=.1))["status"], "pass")

    def test_all_bounded_detail_recipes_are_structurally_valid(self) -> None:
        clusters = (
            build_kettle(),
            build_mug(),
            build_winch(),
            build_stool(),
            build_lantern(),
            build_tied_cargo(),
        )
        for cluster in clusters:
            self.assert_cluster_valid(cluster)

    def test_lantern_keeps_practical_light_as_metadata_not_engine_claim(self) -> None:
        lantern = build_lantern(center=(1, 2, 3), size=.8)
        self.assertEqual(len(lantern.practical_lights), 1)
        light = lantern.receipt["practical_lights"][0]
        self.assertEqual(light["position"], [1.0, 2.0, 3.0])
        self.assertIn("target engine", light["note"])
        self.assertFalse(lantern.receipt["truth_boundary"]["light_metadata_is_engine_light"])

    def test_detail_recipes_are_deterministic(self) -> None:
        first = build_tied_cargo(center=(.2, .1, -.3), size=.75)
        second = build_tied_cargo(center=(.2, .1, -.3), size=.75)
        self.assertEqual(first.receipt["receipt_digest"], second.receipt["receipt_digest"])
        self.assertEqual(first.combined_mesh().vertices, second.combined_mesh().vertices)
        self.assertEqual(first.combined_mesh().faces, second.combined_mesh().faces)

    def test_detail_cluster_is_visible_to_existing_preview_evidence_path(self) -> None:
        cluster = build_kettle(center=(0, .4, 0), size=2.0)
        with tempfile.TemporaryDirectory() as td:
            report = write_preview(cluster.combined_mesh(), Path(td) / "preview", size=72)
            self.assertEqual(len(report["views"]), 3)
            self.assertTrue((Path(td) / "preview" / "front-silhouette.png").is_file())
            self.assertTrue((Path(td) / "preview" / "side-normal.png").is_file())

    def test_authored_parameters_change_geometry_and_identity(self) -> None:
        small = build_winch(radius=.15, cable_drop=.5)
        large = build_winch(radius=.28, cable_drop=1.1)
        self.assertNotEqual(small.receipt["receipt_digest"], large.receipt["receipt_digest"])
        self.assertNotEqual(small.combined_mesh().vertices, large.combined_mesh().vertices)


if __name__ == "__main__":
    unittest.main()
