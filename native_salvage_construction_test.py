#!/usr/bin/env python3
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from native_preview import write_preview
from native_salvage_construction import (
    SalvageConstructionError,
    cloth_patch,
    corrugated_sheet,
    write_piece,
)
from native_uv import validate_uv


class NativeSalvageConstructionTests(unittest.TestCase):
    def test_corrugated_sheet_is_closed_real_geometry_with_uvs(self) -> None:
        piece = corrugated_sheet(
            name="workshop-corrugated-panel",
            width=1.4,
            height=0.9,
            thickness=0.018,
            seed=17,
            subdivisions_x=24,
            subdivisions_y=8,
        )
        topology = piece.receipt["topology"]
        self.assertEqual(topology["invalid_indices"], 0)
        self.assertEqual(topology["degenerate_faces"], 0)
        self.assertTrue(topology["closed_two_manifold_candidate"])
        self.assertEqual(validate_uv(piece.mesh, piece.uvmap)["status"], "pass")
        zs = [vertex[2] for vertex in piece.mesh.vertices]
        self.assertGreater(max(zs) - min(zs), 0.04)
        self.assertEqual(piece.receipt["coordinate_system"], "Y-up")
        self.assertFalse(piece.receipt["truth_boundary"]["physics_simulation"])

    def test_corrugated_sheet_is_seed_deterministic(self) -> None:
        first = corrugated_sheet(width=1.1, height=0.8, seed=23, subdivisions_x=20)
        second = corrugated_sheet(width=1.1, height=0.8, seed=23, subdivisions_x=20)
        other = corrugated_sheet(width=1.1, height=0.8, seed=24, subdivisions_x=20)
        self.assertEqual(first.mesh.vertices, second.mesh.vertices)
        self.assertEqual(first.mesh.faces, second.mesh.faces)
        self.assertEqual(first.uvmap.uvs, second.uvmap.uvs)
        self.assertEqual(first.receipt["receipt_digest"], second.receipt["receipt_digest"])
        self.assertNotEqual(first.mesh.vertices, other.mesh.vertices)

    def test_cloth_keeps_pinned_centerline_corners_and_sags(self) -> None:
        corners = (
            (-1.0, 1.8, -0.7),
            (1.0, 1.8, -0.7),
            (-1.0, 1.8, 0.7),
            (1.0, 1.8, 0.7),
        )
        piece = cloth_patch(
            corners,
            name="blue-workshop-tarp",
            sag=0.24,
            flutter=0.018,
            edge_sag=0.035,
            corner_folds=0.025,
            subdivisions=(18, 14),
        )
        self.assertEqual(piece.receipt["spec"]["pinned_corners"], [list(row) for row in corners])
        self.assertLess(piece.receipt["spec"]["center_vertical_displacement"], -0.20)
        self.assertTrue(piece.receipt["topology"]["closed_two_manifold_candidate"])
        self.assertEqual(piece.receipt["uv"]["status"], "pass")
        self.assertFalse(piece.receipt["truth_boundary"]["cloth_solver"])
        self.assertTrue(piece.receipt["truth_boundary"]["rest_plane_thickness_approximation"])

    def test_cloth_parameters_create_distinct_but_deterministic_geometry(self) -> None:
        corners = ((-1, 1, -1), (1, 1, -1), (-1, 1, 1), (1, 1, 1))
        calm_a = cloth_patch(corners, sag=0.15, flutter=0.0, subdivisions=(10, 8))
        calm_b = cloth_patch(corners, sag=0.15, flutter=0.0, subdivisions=(10, 8))
        worn = cloth_patch(corners, sag=0.15, flutter=0.03, corner_folds=0.04, subdivisions=(10, 8))
        self.assertEqual(calm_a.mesh.vertices, calm_b.mesh.vertices)
        self.assertEqual(calm_a.receipt["receipt_digest"], calm_b.receipt["receipt_digest"])
        self.assertNotEqual(calm_a.mesh.vertices, worn.mesh.vertices)

    def test_native_preview_can_observe_both_donor_surfaces(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            sheet = corrugated_sheet(width=1.0, height=0.8, seed=4, subdivisions_x=18)
            tarp = cloth_patch(
                ((-1, 1.4, -0.6), (1, 1.4, -0.6), (-1, 1.4, 0.6), (1, 1.4, 0.6)),
                sag=0.18,
                subdivisions=(10, 8),
            )
            sheet_report = write_preview(sheet.mesh, root / "sheet-preview", size=48)
            tarp_report = write_preview(tarp.mesh, root / "tarp-preview", size=48)
            self.assertEqual(len(sheet_report["views"]), 3)
            self.assertEqual(len(tarp_report["views"]), 3)
            self.assertTrue(all(view["covered_pixels"] > 0 for view in sheet_report["views"]))
            self.assertTrue(all(view["covered_pixels"] > 0 for view in tarp_report["views"]))

    def test_write_piece_is_create_only_and_preserves_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            piece = corrugated_sheet(width=0.8, height=0.6, seed=8, subdivisions_x=18)
            obj = root / "panel.obj"
            receipt = root / "panel-receipt.json"
            write_piece(piece, obj, receipt)
            self.assertTrue(obj.is_file())
            self.assertTrue(receipt.is_file())
            with self.assertRaises(SalvageConstructionError):
                write_piece(piece, obj, receipt)

    def test_invalid_or_degenerate_inputs_are_rejected(self) -> None:
        with self.assertRaises(SalvageConstructionError):
            corrugated_sheet(width=0.0)
        with self.assertRaises(SalvageConstructionError):
            cloth_patch(((0, 0, 0), (1, 0, 0), (0, 0, 0), (1, 0, 0)))


if __name__ == "__main__":
    unittest.main()
