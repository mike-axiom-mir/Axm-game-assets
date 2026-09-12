#!/usr/bin/env python3
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from native_collision_contract import (
    CollisionBox,
    CollisionContract,
    collision_proxy_mesh,
    coarse_contract_from_mesh,
    contract_payload,
    validate_collision_contract,
    write_collision_contract,
)
from native_construction_kit import rounded_box
from native_geometry import topology_report
from native_preview import write_preview


class NativeCollisionContractTests(unittest.TestCase):
    def test_explicit_vehicle_contract_preserves_roles_and_navigation_footprints(self) -> None:
        contract = CollisionContract(
            "salvage-truck",
            (
                CollisionBox("body", (0, 1.0, 0), (2.0, 1.8, 3.5), "vehicle-proxy"),
                CollisionBox("bumper", (0, .65, 1.9), (2.2, .35, .3), "solid"),
            ),
        )
        report = validate_collision_contract(contract)
        self.assertEqual(report["status"], "pass")
        payload = contract_payload(contract)
        self.assertEqual(payload["boxes"][0]["role"], "vehicle-proxy")
        self.assertEqual(len(payload["navigation_polygons_xz"]), 2)
        self.assertEqual(payload["navigation_polygons_xz"][0][0], [-1.0, -1.75])
        mesh = collision_proxy_mesh(contract)
        topo = topology_report(mesh)
        self.assertEqual(topo["invalid_indices"], 0)
        self.assertEqual(topo["degenerate_faces"], 0)

    def test_conditional_gate_proxy_remains_explicit(self) -> None:
        contract = CollisionContract(
            "gate",
            (
                CollisionBox("left-post", (-1.2, 1, 0), (.4, 2, .5), "solid"),
                CollisionBox("right-post", (1.2, 1, 0), (.4, 2, .5), "solid"),
                CollisionBox("door", (0, 1, 0), (2.0, 1.8, .35), "gate-closed-only", "active only while gate state is closed"),
            ),
        )
        payload = contract_payload(contract)
        self.assertEqual(payload["conditional_roles"], {"door": "active only while gate state is closed"})
        self.assertFalse(payload["truth_boundary"]["physics_engine_tested"])
        self.assertFalse(payload["truth_boundary"]["pathfinding_tested"])

    def test_aabb_helper_stays_explicitly_coarse(self) -> None:
        mesh = rounded_box((0, 1, 0), (4, 2, 3), chamfer=.1, name="building")
        contract = coarse_contract_from_mesh(mesh, asset_id="building", scale=(.75, .9, .65))
        payload = contract_payload(contract)
        self.assertIn("Not an automatic production collider fit", payload["basis"])
        self.assertEqual(payload["boxes"][0]["role"], "coarse-placement-proxy")
        self.assertEqual(payload["boxes"][0]["size"], [3.0, 1.8, 1.9500000000000002])

    def test_invalid_boxes_are_rejected(self) -> None:
        bad = CollisionContract("bad", (CollisionBox("x", (0, 0, 0), (1, -1, 1)),))
        report = validate_collision_contract(bad)
        self.assertEqual(report["status"], "fail")
        duplicate = CollisionContract("bad", (CollisionBox("x", (0, 0, 0), (1, 1, 1)), CollisionBox("x", (2, 0, 0), (1, 1, 1))))
        self.assertEqual(validate_collision_contract(duplicate)["status"], "fail")

    def test_written_contract_is_create_only_and_previewable(self) -> None:
        contract = CollisionContract(
            "machine",
            (
                CollisionBox("base", (0, .4, 0), (2.2, .8, 1.6), "solid"),
                CollisionBox("tower", (.6, 1.6, 0), (.65, 1.7, .7), "machine-envelope"),
            ),
        )
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "collision"
            receipt = write_collision_contract(contract, root)
            self.assertEqual(receipt["status"], "PASS")
            self.assertFalse(receipt["authority"]["physics_acceptance"])
            self.assertFalse(receipt["authority"]["canon"])
            payload = json.loads((root / "collision-contract.json").read_text())
            self.assertEqual(payload["asset_id"], "machine")
            preview = write_preview(collision_proxy_mesh(contract), Path(td) / "preview", size=64)
            self.assertEqual(len(preview["views"]), 3)
            with self.assertRaises(FileExistsError):
                write_collision_contract(contract, root)


if __name__ == "__main__":
    unittest.main()
