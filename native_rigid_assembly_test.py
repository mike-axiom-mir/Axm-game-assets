#!/usr/bin/env python3
from __future__ import annotations

import copy
import math
import struct
import tempfile
import unittest
from pathlib import Path

from native_construction_kit import rounded_box, torus_ring
from native_multi_gltf import MaterialPrimitive
from native_rigid_assembly import (
    RigidAssembly,
    RigidAssemblyError,
    RigidComponent,
    RigidMotion,
    RigidSocket,
    compile_rigid_assembly_gltf,
    validate_rigid_assembly_delivery,
    write_rigid_assembly_gltf,
)
from native_surface_families import write_surface_family
from native_uv import box_project_world


def primitive(mesh, material: str = "salvage") -> MaterialPrimitive:
    return MaterialPrimitive(
        mesh=mesh,
        uvmap=box_project_world(mesh, world_units_per_tile=.25),
        material_name=material,
        base_color_uri="textures/base_color.png",
        normal_uri="textures/normal.png",
        orm_uri="textures/orm.png",
    )


def fixture() -> RigidAssembly:
    body_mesh = rounded_box((0, 1.0, 0), (2.0, .8, 3.0), chamfer=.12, name="body-geometry")
    left_mesh = torus_ring((-1.0, .62, .95), radius=.42, tube=.12, axis="x", name="wheel-left")
    right_mesh = torus_ring((1.0, .62, .95), radius=.42, tube=.12, axis="x", name="wheel-right")
    turret_mesh = rounded_box((0, 1.65, .25), (.85, .35, .95), chamfer=.07, name="turret-geometry")
    return RigidAssembly(
        "donor-rig",
        components=(
            RigidComponent("body", (0, 1.0, 0), (primitive(body_mesh, "body"),), "vehicle-body"),
            RigidComponent("wheel-left", (-1.0, .62, .95), (primitive(left_mesh, "rubber"),), "drive-wheel"),
            RigidComponent("wheel-right", (1.0, .62, .95), (primitive(right_mesh, "rubber"),), "drive-wheel"),
            RigidComponent("turret", (0, 1.65, .25), (primitive(turret_mesh, "turret"),), "aiming-mechanism"),
        ),
        motions=(
            RigidMotion("drive", "wheel-left", (1, 0, 0), (0, math.pi / 2, math.pi, math.pi * 1.5, math.tau), 1.0),
            RigidMotion("drive", "wheel-right", (1, 0, 0), (0, math.pi / 2, math.pi, math.pi * 1.5, math.tau), 1.0),
            RigidMotion("aim", "turret", (0, 1, 0), (-.5, 0, .5, 0, -.5), 4.0),
        ),
        sockets=(
            RigidSocket("hitch", "body", (0, -.2, -1.52), (0, 0, -1)),
            RigidSocket("muzzle", "turret", (0, 0, .52), (0, 0, 1)),
        ),
    )


class NativeRigidAssemblyTests(unittest.TestCase):
    def test_compile_preserves_components_motion_and_sockets(self) -> None:
        assembly = fixture()
        document, binary = compile_rigid_assembly_gltf(assembly, buffer_uri="donor-rig.bin")
        report = validate_rigid_assembly_delivery(document, binary)
        self.assertEqual(report["status"], "pass", report)
        self.assertEqual(report["components"], 4)
        self.assertEqual(report["motions"], 3)
        self.assertEqual(report["sockets"], 2)
        self.assertEqual({animation["name"] for animation in document["animations"]}, {"aim", "drive"})
        by_name = {node["name"]: node for node in document["nodes"]}
        self.assertEqual(by_name["wheel-left"]["translation"], [-1.0, .62, .95])
        self.assertEqual(by_name["turret"]["extras"]["semantic_role"], "aiming-mechanism")
        self.assertFalse("skins" in document)

    def test_delivery_is_deterministic(self) -> None:
        first_doc, first_binary = compile_rigid_assembly_gltf(fixture(), buffer_uri="asset.bin")
        second_doc, second_binary = compile_rigid_assembly_gltf(fixture(), buffer_uri="asset.bin")
        self.assertEqual(first_doc, second_doc)
        self.assertEqual(first_binary, second_binary)

    def test_digest_tamper_is_rejected(self) -> None:
        document, binary = compile_rigid_assembly_gltf(fixture(), buffer_uri="asset.bin")
        tampered = copy.deepcopy(document)
        tampered["extras"]["axmRigidAssembly"]["sockets"][0]["position"][0] += .25
        report = validate_rigid_assembly_delivery(tampered, binary)
        self.assertEqual(report["status"], "fail")
        self.assertIn("rigid assembly digest mismatch", report["failures"])

    def test_motion_payload_tamper_is_rejected(self) -> None:
        document, binary = compile_rigid_assembly_gltf(fixture(), buffer_uri="asset.bin")
        altered = bytearray(binary)
        animation = next(item for item in document["animations"] if item["name"] == "aim")
        accessor_index = animation["samplers"][0]["output"]
        accessor = document["accessors"][accessor_index]
        view = document["bufferViews"][accessor["bufferView"]]
        offset = view.get("byteOffset", 0) + accessor.get("byteOffset", 0)
        struct.pack_into("<f", altered, offset, .5)
        report = validate_rigid_assembly_delivery(document, bytes(altered))
        self.assertEqual(report["status"], "fail")
        self.assertTrue(any("quaternion" in failure for failure in report["failures"]))

    def test_invalid_authoring_state_is_rejected_before_compile(self) -> None:
        base = fixture()
        duplicate = RigidAssembly(base.name, base.components, base.motions + (base.motions[0],), base.sockets)
        with self.assertRaises(RigidAssemblyError):
            compile_rigid_assembly_gltf(duplicate, buffer_uri="asset.bin")
        zero_axis = RigidAssembly(base.name, base.components, (RigidMotion("bad", "turret", (0, 0, 0), (0, 1), 1),), base.sockets)
        with self.assertRaises(RigidAssemblyError):
            compile_rigid_assembly_gltf(zero_axis, buffer_uri="asset.bin")
        bad_socket = RigidAssembly(base.name, base.components, (), (RigidSocket("x", "missing", (0, 0, 0)),))
        with self.assertRaises(RigidAssemblyError):
            compile_rigid_assembly_gltf(bad_socket, buffer_uri="asset.bin")

    def test_real_surface_family_can_be_written_with_rigid_delivery(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "delivery"
            write_surface_family(root / "textures", kind="salvage_metal", size=16, seed=91)
            receipt = write_rigid_assembly_gltf(fixture(), root)
            self.assertEqual(receipt["status"], "PASS")
            self.assertEqual(receipt["validation"]["status"], "pass")
            self.assertFalse(receipt["authority"]["automatic_genome_mutation"])
            self.assertFalse(receipt["authority"]["canon"])
            self.assertTrue((root / "donor-rig.gltf").is_file())
            self.assertTrue((root / "donor-rig.bin").is_file())
            self.assertTrue((root / "rigid-assembly-receipt.json").is_file())
            with self.assertRaises(FileExistsError):
                write_rigid_assembly_gltf(fixture(), root)


if __name__ == "__main__":
    unittest.main()
