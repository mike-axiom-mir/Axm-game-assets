#!/usr/bin/env python3
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from native_construction_kit import (
    ConstructionKitError,
    beam_segment,
    build_barrel,
    build_crane,
    build_crate,
    build_ladder,
    build_railing,
    lathe_profile,
    pipe_path,
    torus_ring,
)
from native_geometry import topology_report
from native_preview import write_preview
from native_uv import box_project_world, validate_uv


class NativeConstructionKitTests(unittest.TestCase):
    def assert_closed(self, mesh) -> None:
        report = topology_report(mesh)
        self.assertEqual(report["invalid_indices"], 0)
        self.assertEqual(report["degenerate_faces"], 0)
        self.assertEqual(report["boundary_edges"], 0)
        self.assertEqual(report["nonmanifold_edges"], 0)
        self.assertTrue(report["closed_two_manifold_candidate"])

    def test_generic_primitives_are_closed_and_uv_projectable(self) -> None:
        meshes = [
            beam_segment((0, 0, 0), (1.2, 1.0, .7), width=.12, depth=.08),
            pipe_path(((0, 0, 0), (.2, .8, .3), (1.1, 1.2, .5)), radius=.07, sides=9),
            torus_ring((0, 0, 0), radius=.6, tube=.09, axis="z", major_segments=18, minor_segments=7),
            lathe_profile(((0, 0), (.4, .1), (.5, .8), (.35, 1.2), (0, 1.2)), segments=16),
        ]
        for mesh in meshes:
            self.assert_closed(mesh)
            self.assertEqual(validate_uv(mesh, box_project_world(mesh))["status"], "pass")

    def test_semantic_assemblies_keep_material_and_role_identity(self) -> None:
        for assembly in (build_ladder(), build_barrel(), build_crate(), build_railing((0, 0, 0), (2.4, 0, .4)), build_crane(height=2.8, boom_length=1.8)):
            self.assertGreater(len(assembly.parts), 1)
            self.assertEqual(assembly.receipt["schema"], "axm.game-assets.native-construction-kit/v0.1")
            self.assertFalse(assembly.receipt["truth_boundary"]["automatic_genome_mutation"])
            self.assertFalse(assembly.receipt["truth_boundary"]["automatic_canon"])
            self.assertIn("a5cc708457b7e8f33e794fdac648ae65d15a0fb4", assembly.receipt["provenance"]["donor"]["commit"])
            self.assertEqual(len({part.part_id for part in assembly.parts}), len(assembly.parts))
            for part in assembly.parts:
                self.assertTrue(part.material_family)
                self.assertTrue(part.semantic_role)
                self.assert_closed(part.mesh)

    def test_crane_is_deterministic_and_observable_by_existing_preview(self) -> None:
        first = build_crane(height=2.6, boom_length=1.7)
        second = build_crane(height=2.6, boom_length=1.7)
        self.assertEqual(first.receipt["receipt_digest"], second.receipt["receipt_digest"])
        self.assertEqual(first.combined_mesh().vertices, second.combined_mesh().vertices)
        self.assertEqual(first.combined_mesh().faces, second.combined_mesh().faces)
        with tempfile.TemporaryDirectory() as td:
            report = write_preview(first.combined_mesh(), Path(td) / "preview", size=64)
            self.assertEqual(len(report["views"]), 3)
            for view in ("front", "side", "top"):
                for signal in ("silhouette", "depth", "normal"):
                    self.assertTrue((Path(td) / "preview" / f"{view}-{signal}.png").is_file())

    def test_pipe_rejects_zero_length_segments(self) -> None:
        with self.assertRaises(ConstructionKitError):
            pipe_path(((0, 0, 0), (0, 0, 0)), radius=.1)

    def test_lathe_rejects_ambiguous_double_axis_point(self) -> None:
        with self.assertRaises(ConstructionKitError):
            lathe_profile(((0, 0), (0, 1), (.2, 1.4)))

    def test_railing_changes_with_authored_span(self) -> None:
        short = build_railing((0, 0, 0), (1.0, 0, 0), post_spacing=.5)
        long = build_railing((0, 0, 0), (3.0, 0, 0), post_spacing=.5)
        self.assertGreater(len(long.parts), len(short.parts))
        self.assertNotEqual(long.receipt["receipt_digest"], short.receipt["receipt_digest"])


if __name__ == "__main__":
    unittest.main()
