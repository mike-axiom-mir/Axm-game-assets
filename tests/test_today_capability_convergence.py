#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]

from asset_intent_router import route_asset_intent
from native_character_source_profile import (
    CharacterSourceProfileError,
    compile_character_source_profile,
)
from native_form_recipe import FormRecipeError, compile_form_recipe
from native_geometry import bounds, topology_report
from native_construction_kit import ConstructionAssembly, SemanticPart
from native_reusable_part_library import (
    discover_assembly_parts,
    geometry_digest,
    load_geometry_atom,
    pull_assembly_parts,
)
from native_material_response import (
    MaterialResponseError,
    material_response_catalog,
    resolve_material_response,
)
from universal_creation_asset_bridge import (
    SOURCE_PROPOSAL_SCHEMA,
    UniversalCreationIngressError,
    build_universal_creation_source_proposal,
)


def _glb() -> bytes:
    document = {
        "asset": {"version": "2.0"},
        "scenes": [{"nodes": [0]}],
        "scene": 0,
        "nodes": [{"mesh": 0}],
        "meshes": [{"primitives": []}],
        "materials": [{"name": "wood"}],
    }
    payload = json.dumps(document, sort_keys=True, separators=(",", ":")).encode("utf-8")
    while len(payload) % 4:
        payload += b" "
    total = 12 + 8 + len(payload)
    return (
        struct.pack("<4sII", b"glTF", 2, total)
        + struct.pack("<II", len(payload), 0x4E4F534A)
        + payload
    )


def _canonical(value) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def _form_recipe() -> dict:
    return {
        "schema": "axm.game-assets.form-recipe/v0.1",
        "name": "bonsai-form-proof",
        "definitions": {
            "branch": {
                "params": {"rise": 0.62, "radius": 0.035},
                "defaults": {
                    "material_family": "wood",
                    "semantic_role": "branch",
                },
                "parts": [
                    {
                        "id": "stem",
                        "pattern": "pipe",
                        "path": [
                            [0, 0, 0],
                            [0.08, 0.35, 0],
                            [0.16, {"$var": "rise"}, 0.05]
                        ],
                        "radius": {"$var": "radius"},
                        "segments": 8,
                    }
                ],
            }
        },
        "parts": [
            {
                "id": "trunk",
                "pattern": "loft",
                "sections": [
                    {"at": 0.0, "radius": [0.22, 0.18]},
                    {"at": 0.55, "radius": [0.30, 0.22], "offset": [0.02, 0.0]},
                    {"at": 1.0, "radius": [0.20, 0.15], "offset": [-0.02, 0.01]},
                ],
                "segments": 16,
                "material_family": "wood",
                "semantic_role": "trunk",
            },
            {
                "repeat": 2,
                "step": [0.18, 0.12, 0.0],
                "body": [
                    {
                        "use": "branch",
                        "id_prefix": "branch-",
                        "rotation": [0.0, 0.0, 0.25],
                    }
                ],
            },
            {
                "use": "branch",
                "id_prefix": "special-",
                "with": {"rise": 0.92, "radius": 0.05},
                "translation": [-0.22, 0.18, 0.0],
                "rotation": [0.0, 0.0, -0.35]
            },
            {
                "id": "brooch",
                "pattern": "profile-extrude",
                "outline": [[-0.05, -0.06], [0.06, -0.02], [0.04, 0.07], [-0.04, 0.06]],
                "depth": 0.02,
                "translation": [0.0, -0.20, 0.70],
                "material_family": "bronze",
                "semantic_role": "clothing-fastener",
            },
        ],
    }


class TodayConvergenceTests(unittest.TestCase):
    def test_intent_router_selects_one_family_without_executing_or_mutating(self) -> None:
        plan = route_asset_intent({
            "schema": "axm.game-assets.asset-intent/v0.1",
            "prompt": "Create a playable character asset with rigged motion and detailed materials",
            "asset_id": "tree-person",
            "deliverables": ["GLB", "source state"],
            "requirements": ["rigged", "Godot runtime"],
        })
        self.assertEqual(plan["status"], "PLANNED_NOT_EXECUTED")
        self.assertEqual(plan["selected_family"], "character")
        ids = [row["id"] for row in plan["production_blocks"]]
        self.assertIn("character-source-profile", ids)
        self.assertIn("rig-skin-motion", ids)
        self.assertIn("material-response", ids)
        self.assertIn("runtime-validation", ids)
        self.assertFalse(plan["automatic_execution"])
        self.assertFalse(plan["automatic_genome_mutation"])
        self.assertFalse(plan["automatic_vault_admission"])
        self.assertFalse(plan["automatic_canon"])

    def test_forge_cli_exposes_intent_route_without_executing_asset_build(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            request = Path(td) / "intent.json"
            request.write_text(json.dumps({
                "schema": "axm.game-assets.asset-intent/v0.1",
                "prompt": "Create a vegetation tree asset with detailed leaves",
                "asset_id": "tree-proof",
            }), encoding="utf-8")
            completed = subprocess.run(
                [sys.executable, str(ROOT / "forge.py"), "route-intent", str(request)],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            result = json.loads(completed.stdout)
            self.assertEqual(result["status"], "PLANNED_NOT_EXECUTED")
            self.assertEqual(result["selected_family"], "vegetation")
            self.assertFalse(result["automatic_execution"])

    def test_intent_router_holds_ambiguous_multi_family_language(self) -> None:
        result = route_asset_intent({
            "prompt": "Create a character holding a rifle weapon",
        })
        self.assertEqual(result["status"], "HOLD_AMBIGUOUS_FAMILY")
        self.assertEqual(
            {row["family"] for row in result["candidates"]},
            {"character", "weapon"},
        )
        self.assertFalse(result["automatic_execution"])

    def test_intent_router_explicit_family_wins_without_fuzzy_guess(self) -> None:
        result = route_asset_intent({
            "prompt": "A strange living tower creature",
            "family": "building",
        })
        self.assertEqual(result["selected_family"], "building")
        self.assertEqual(result["selection_basis"], "caller-explicit-family")

    def test_material_response_catalog_and_hold_boundary(self) -> None:
        catalog = material_response_catalog()
        self.assertEqual(catalog["counts"], {"families": 13, "organs": 8})
        value = resolve_material_response("wood-oiled")
        self.assertIn("surface.anisotropy", value["active_organs"])
        self.assertIn("surface.subsurface", value["active_organs"])
        self.assertEqual(value["renderer_binding"], "HOLD_RENDERER_BINDING_NOT_TESTED")
        with self.assertRaises(MaterialResponseError):
            resolve_material_response("invented-family")

    def test_form_recipe_composes_reusable_new_forms_and_retains_source_receipt(self) -> None:
        recipe = _form_recipe()
        before = json.loads(json.dumps(recipe))
        assembly = compile_form_recipe(recipe)
        self.assertEqual(recipe, before)
        self.assertEqual(assembly.receipt["schema"], "axm.game-assets.form-recipe/v0.1")
        self.assertTrue(assembly.receipt["source_authority"])
        self.assertFalse(assembly.receipt["truth_boundary"]["automatic_genome_mutation"])
        self.assertFalse(assembly.receipt["truth_boundary"]["automatic_vault_admission"])
        self.assertEqual(assembly.receipt["definitions_declared"], 1)
        self.assertEqual(assembly.receipt["parameterized_definitions"], 1)
        self.assertEqual(assembly.receipt["part_count"], 5)
        self.assertEqual(len({part.part_id for part in assembly.parts}), 5)
        by_id = {part.part_id: part for part in assembly.parts}
        default_bounds = bounds(by_id["r0-branch-stem"].mesh)
        special_bounds = bounds(by_id["special-stem"].mesh)
        self.assertGreater(
            special_bounds[1][1] - special_bounds[0][1],
            default_bounds[1][1] - default_bounds[0][1],
        )
        report = topology_report(assembly.combined_mesh())
        self.assertEqual(report["invalid_indices"], 0)
        self.assertEqual(report["degenerate_faces"], 0)
        self.assertGreater(report["triangles"], 100)

    def test_form_recipe_rejects_undeclared_parameter_override(self) -> None:
        recipe = _form_recipe()
        recipe["parts"] = [
            {"use": "branch", "with": {"not_declared": 1.0}}
        ]
        with self.assertRaises(FormRecipeError):
            compile_form_recipe(recipe)

    def test_form_recipe_rejects_missing_definition(self) -> None:
        recipe = _form_recipe()
        recipe["parts"] = [{"use": "missing"}]
        with self.assertRaises(FormRecipeError):
            compile_form_recipe(recipe)

    def test_reusable_part_scan_does_not_auto_admit_and_selected_pull_survives_source(self) -> None:
        assembly = compile_form_recipe(_form_recipe())
        with tempfile.TemporaryDirectory() as td:
            library = Path(td) / "library"
            scan = discover_assembly_parts(assembly, library_root=library)
            self.assertFalse(scan["library_mutated"])
            self.assertFalse(library.exists())
            self.assertEqual(scan["candidate_count"], len(assembly.parts))

            selected = assembly.parts[0]
            pull = pull_assembly_parts(assembly, library, [selected.part_id])
            self.assertEqual(pull["selected_part_ids"], [selected.part_id])
            self.assertFalse(pull["automatic_admission"])
            self.assertFalse(pull["source_asset_mutated"])
            self.assertEqual(pull["created_geometry_atoms"], 1)
            self.assertEqual(pull["created_semantic_items"], 1)

            digest = geometry_digest(selected.mesh)
            del assembly
            restored = load_geometry_atom(library, digest, name="restored")
            report = topology_report(restored)
            self.assertEqual(report["invalid_indices"], 0)
            self.assertEqual(report["degenerate_faces"], 0)
            self.assertGreater(report["triangles"], 0)

    def test_reusable_part_library_dedups_geometry_separately_from_material_labels(self) -> None:
        base = compile_form_recipe(_form_recipe()).parts[0].mesh
        assembly = ConstructionAssembly(
            "same-shape-different-style",
            (
                SemanticPart("red", base, "paint-red", "panel"),
                SemanticPart("blue", base, "paint-blue", "panel"),
            ),
            {"receipt_digest": "sha256:" + "0" * 64},
        )
        with tempfile.TemporaryDirectory() as td:
            result = pull_assembly_parts(assembly, Path(td) / "library", ["red", "blue"])
            self.assertEqual(result["created_geometry_atoms"], 1)
            self.assertEqual(result["reused_geometry_atoms"], 1)
            self.assertEqual(result["created_semantic_items"], 2)
            index = json.loads((Path(td) / "library" / "library.json").read_text(encoding="utf-8"))
            self.assertEqual(index["counts"]["geometry_objects"], 1)
            self.assertEqual(index["counts"]["semantic_items"], 2)
            self.assertFalse(index["automatic_admission"])

    def test_character_source_profile_carries_race_clothing_sockets_and_material_intent(self) -> None:
        profile = compile_character_source_profile({
            "schema": "axm.game-assets.character-source-profile/v0.1",
            "asset_id": "bonsai-race-proof",
            "race_id": "bonsai-nature-race",
            "body_family": "rooted-small-tree",
            "parts": [
                {"id": "trunk", "role": "trunk"},
                {"id": "hand-r", "role": "hand"},
                {"id": "canopy", "role": "canopy"},
            ],
            "sockets": [
                {
                    "id": "tool-r",
                    "part": "hand-r",
                    "position": [0.0, 0.0, 0.0],
                    "purpose": "right-hand tool",
                    "tags": ["tool", "weapon"],
                }
            ],
            "clothing_regions": [
                {
                    "id": "torso-wrap",
                    "parts": ["trunk"],
                    "body_family": "rooted-small-tree",
                    "attachment_tags": ["wrap", "belt"],
                }
            ],
            "material_responses": {
                "default": {"family": "wood-oiled"},
                "canopy": {"family": "leaf-thin"},
            },
        })
        self.assertEqual(profile["race_id"], "bonsai-nature-race")
        self.assertEqual(profile["body_family"], "rooted-small-tree")
        self.assertEqual(profile["sockets"][0]["id"], "tool-r")
        self.assertEqual(profile["clothing_regions"][0]["fit_truth"], "DECLARED_REGION_ONLY_NOT_GEOMETRIC_FIT_PROOF")
        self.assertEqual(
            profile["material_response_holds"], ["canopy", "default"]
        )
        self.assertFalse(profile["truth_boundary"]["clothing_fit_proven"])
        self.assertFalse(profile["truth_boundary"]["automatic_vault_admission"])

    def test_character_source_profile_rejects_unknown_socket_part(self) -> None:
        with self.assertRaises(CharacterSourceProfileError):
            compile_character_source_profile({
                "schema": "axm.game-assets.character-source-profile/v0.1",
                "asset_id": "bad",
                "race_id": "tree",
                "body_family": "tree",
                "parts": [{"id": "trunk", "role": "body"}],
                "sockets": [{"id": "bad", "part": "ghost", "position": [0, 0, 0]}],
            })

    def test_source_first_uc_ingress_preserves_structure_without_authority(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            asset = root / "bonsai.glb"
            body = _glb()
            asset.write_bytes(body)
            source = {
                "schema": "axm.creator-source/v1",
                "kind": "whole-character-recipe",
                "source_authority": True,
                "realization_is_secondary": True,
                "automatic_canon_admission": False,
                "recipe": {
                    "schema": "axm.character-recipe/v0.1",
                    "name": "display-name-not-an-asset-id",
                },
                "recipe_sha256": "0" * 64,
                "character": {
                    "race_id": "bonsai-nature-race",
                    "body_family": "rooted-small-tree",
                },
                "parts_index": [
                    {"id": "trunk", "role": "trunk", "pattern": "loft"}
                ],
                "sockets": [
                    {"id": "tool-r", "part": "trunk", "position": [0, 0, 0]}
                ],
                "clothing_regions": [
                    {"id": "wrap", "parts": ["trunk"], "body_family": "rooted-small-tree"}
                ],
                "material_intent": {"response": {"family": "wood-oiled"}},
                "material_response_status": "HOLD_RENDERER_BINDING_NOT_TESTED",
                "rig_status": "NOT_PRESENT",
                "animation_status": "NOT_PRESENT",
                "compiled_specification": {"schema": "axm.surface-3d/v0.1"},
                "artifact": {
                    "path": "/provider/local/bonsai.glb",
                    "sha256": hashlib.sha256(body).hexdigest(),
                    "specification_sha256": "1" * 64,
                },
                "truth_boundary": "test fixture",
            }
            source["source_sha256"] = hashlib.sha256(_canonical(source)).hexdigest()
            sidecar = asset.with_suffix(".glb.source.json")
            sidecar.write_text(
                json.dumps(source, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            proposal = build_universal_creation_source_proposal(
                asset, expected_asset_id="bonsai-race-proof"
            )
            self.assertEqual(proposal["schema"], SOURCE_PROPOSAL_SCHEMA)
            self.assertEqual(proposal["status"], "PROPOSAL_ONLY")
            self.assertEqual(proposal["asset"]["id"], "bonsai-race-proof")
            retained = proposal["verified_source"]["retained"]
            self.assertEqual(retained["character"]["body_family"], "rooted-small-tree")
            self.assertEqual(retained["sockets"][0]["id"], "tool-r")
            self.assertEqual(
                retained["material_response_status"],
                "HOLD_RENDERER_BINDING_NOT_TESTED",
            )
            self.assertFalse(proposal["authority"]["genome_mutation"])
            self.assertFalse(proposal["authority"]["canon"])
            self.assertEqual(
                proposal["review_readiness"]["visual_acceptance"], "NOT_GRANTED"
            )

    def test_source_first_uc_ingress_rejects_tampered_glb(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            asset = root / "asset.glb"
            body = _glb()
            asset.write_bytes(body)
            source = {
                "schema": "axm.creator-source/v1",
                "kind": "form-pattern",
                "source_authority": True,
                "realization_is_secondary": True,
                "automatic_canon_admission": False,
                "artifact": {
                    "path": "/provider/asset.glb",
                    "sha256": hashlib.sha256(body).hexdigest(),
                    "specification_sha256": "2" * 64,
                },
            }
            source["source_sha256"] = hashlib.sha256(_canonical(source)).hexdigest()
            asset.with_suffix(".glb.source.json").write_text(
                json.dumps(source, sort_keys=True), encoding="utf-8"
            )
            asset.write_bytes(body + b"tamper")
            with self.assertRaisesRegex(
                UniversalCreationIngressError, "INVALID_GLB|SOURCE_ARTIFACT_DIGEST_DRIFT"
            ):
                build_universal_creation_source_proposal(asset)


if __name__ == "__main__":
    unittest.main()
