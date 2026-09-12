#!/usr/bin/env python3
from __future__ import annotations

import unittest

from native_geometry import topology_report
from native_stencil_detail import StencilDetailError, stencil_mesh, stencil_receipt


class NativeStencilDetailTests(unittest.TestCase):
    def test_letters_are_real_geometry(self) -> None:
        mesh, receipt = stencil_receipt(["GOOD", "STUFF"], width=1.6, height=1.2, name="shop-sign")
        self.assertGreater(len(mesh.vertices), 0)
        self.assertGreater(len(mesh.faces), 0)
        report = topology_report(mesh)
        self.assertEqual(report["invalid_indices"], 0)
        self.assertEqual(report["degenerate_faces"], 0)
        self.assertTrue(receipt["truth_boundary"]["geometry_generated"])
        self.assertFalse(receipt["truth_boundary"]["art_direction_approved"])

    def test_same_input_is_deterministic(self) -> None:
        first, r1 = stencil_receipt(["AXM 2040"], width=2.0, height=0.8)
        second, r2 = stencil_receipt(["AXM 2040"], width=2.0, height=0.8)
        self.assertEqual(first.vertices, second.vertices)
        self.assertEqual(first.faces, second.faces)
        self.assertEqual(r1["receipt_digest"], r2["receipt_digest"])

    def test_unknown_characters_are_rejected_not_guessed(self) -> None:
        with self.assertRaises(StencilDetailError):
            stencil_mesh(["HELLO!"])

    def test_requested_bounds_are_respected(self) -> None:
        _, receipt = stencil_receipt(["SURVIVE"], width=1.4, height=0.6)
        lo = receipt["bounds"]["min"]
        hi = receipt["bounds"]["max"]
        self.assertLessEqual(hi[0] - lo[0], 1.4 + 1e-9)
        self.assertLessEqual(hi[1] - lo[1], 0.6 + 1e-9)

    def test_spaces_do_not_emit_cells(self) -> None:
        compact = stencil_mesh(["AA"])
        spaced = stencil_mesh(["A A"])
        self.assertEqual(len(compact.faces), len(spaced.faces))


if __name__ == "__main__":
    unittest.main()
