#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import struct
import tempfile
import unittest

from universal_creation_asset_bridge import (
    PROPOSAL_SCHEMA,
    UniversalCreationIngressError,
    build_universal_creation_proposal,
    write_proposal,
)


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _json_bytes(value: dict) -> bytes:
    return (json.dumps(value, indent=2) + "\n").encode("utf-8")


def _glb(*, meshes: int = 1, materials: int = 1) -> bytes:
    document = {
        "asset": {"version": "2.0"},
        "scenes": [{"nodes": []}],
        "scene": 0,
        "meshes": [{} for _ in range(meshes)],
        "materials": [{} for _ in range(materials)],
    }
    payload = json.dumps(document, sort_keys=True, separators=(",", ":")).encode("utf-8")
    while len(payload) % 4:
        payload += b" "
    total = 12 + 8 + len(payload)
    return b"".join(
        [
            struct.pack("<4sII", b"glTF", 2, total),
            struct.pack("<II", len(payload), 0x4E4F534A),
            payload,
        ]
    )


def _png(width: int = 128, height: int = 96) -> bytes:
    # The bridge intentionally performs a bounded header/IHDR identity check,
    # not a full image decoder. This fixture is therefore enough for that gate.
    return b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\rIHDR" + struct.pack(">II", width, height)


class UniversalCreationAssetBridgeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "candidate"
        self.root.mkdir()
        self._build_candidate()

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _artifact(self, name: str, data: bytes, **extra) -> dict:
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return {
            "path": name,
            "sha256": _sha(data),
            "bytes": len(data),
            **extra,
        }

    def _build_candidate(self) -> None:
        request = {
            "schema": "axm.3d-forge-request/v0.1",
            "asset_id": "stylized-workshop-cluster",
            "faction": "civilian-repair",
            "archetype": "lived-in-workshop-cluster",
            "scale_meters": 4.2,
            "palette": ["weathered-blue", "warm-lamp", "rust-red", "wood"],
            "quality": "hero",
            "loadout": "reference",
            "context_key": "3d/stylized-workshop-cluster/hero",
            "criteria": [
                "readable-primary-silhouette",
                "large-medium-small-form-hierarchy",
                "functional-clutter",
                "material-separation",
            ],
            "constraints": [
                "retain tarp roof and workshop read at RTS camera distance",
                "small detail must support function or history",
            ],
            "avoid": ["sterile symmetry", "detail noise without readable groups"],
            "render": {
                "resolution": 1024,
                "angles_degrees": [0, 90, 180, 270],
                "transparent": False,
            },
            "technical_requirements": {
                "minimum_render_angles": 4,
                "minimum_lod0_triangles": 80000,
            },
        }
        self.request = request
        self.source = self._artifact("source.blend", b"source-state")
        exports = {}
        for index, name in enumerate(("lod0", "lod1", "lod2", "collision")):
            exports[name] = self._artifact(
                f"{name}.glb", _glb(meshes=index + 1, materials=2)
            )
        proofs = [
            self._artifact(
                f"view-{index}.png",
                _png(256, 256),
                angle_degrees=angle,
            )
            for index, angle in enumerate((0, 90, 180, 270))
        ]
        manifest = {
            "asset_id": request["asset_id"],
            "source": self.source,
            "exports": exports,
            "render_proofs": proofs,
        }
        receipt = {
            "schema": "axm.3d-forge-receipt/v0.1",
            "truth_status": "BLENDER_FORGE_EXECUTED_AND_GLB_DECODED",
            "asset_id": request["asset_id"],
            "render_proofs": proofs,
            "acceptance": {
                "technical": "pass",
                "visual": "requires artifact-bound review",
            },
        }
        (self.root / "forge-request.json").write_bytes(_json_bytes(request))
        (self.root / "asset-manifest.json").write_bytes(_json_bytes(manifest))
        (self.root / "forge-receipt.json").write_bytes(_json_bytes(receipt))

    def _load(self, name: str) -> dict:
        return json.loads((self.root / name).read_text(encoding="utf-8"))

    def _write(self, name: str, value: dict) -> None:
        (self.root / name).write_bytes(_json_bytes(value))

    def test_valid_candidate_becomes_proposal_without_authority(self) -> None:
        proposal = build_universal_creation_proposal(
            self.root, expected_asset_id="stylized-workshop-cluster"
        )
        self.assertEqual(proposal["schema"], PROPOSAL_SCHEMA)
        self.assertEqual(proposal["status"], "PROPOSAL_ONLY")
        self.assertEqual(
            proposal["review_readiness"]["multi_angle_distribution"]["status"],
            "PASS",
        )
        self.assertEqual(
            proposal["expression_intent"]["criteria"],
            self.request["criteria"],
        )
        self.assertEqual(
            proposal["verified_exports"]["lod0"]["inspection"]["version"], 2
        )
        self.assertFalse(proposal["authority"]["genome_mutation"])
        self.assertFalse(proposal["authority"]["visual_approval"])
        self.assertFalse(proposal["authority"]["canon"])
        self.assertTrue(proposal["proposal_digest"].startswith("sha256:"))

    def test_tampered_export_is_rejected(self) -> None:
        with (self.root / "lod0.glb").open("ab") as handle:
            handle.write(b"tamper")
        with self.assertRaisesRegex(
            UniversalCreationIngressError, "ARTIFACT_DIGEST_DRIFT"
        ):
            build_universal_creation_proposal(self.root)

    def test_manifest_path_escape_is_rejected(self) -> None:
        manifest = self._load("asset-manifest.json")
        manifest["exports"]["lod0"]["path"] = "../outside.glb"
        self._write("asset-manifest.json", manifest)
        with self.assertRaisesRegex(UniversalCreationIngressError, "UNSAFE_PATH"):
            build_universal_creation_proposal(self.root)

    def test_identity_drift_is_rejected(self) -> None:
        receipt = self._load("forge-receipt.json")
        receipt["asset_id"] = "different-asset"
        self._write("forge-receipt.json", receipt)
        with self.assertRaisesRegex(
            UniversalCreationIngressError, "ASSET_IDENTITY_DRIFT"
        ):
            build_universal_creation_proposal(self.root)

    def test_receipt_proof_drift_is_rejected(self) -> None:
        receipt = self._load("forge-receipt.json")
        receipt["render_proofs"] = list(reversed(receipt["render_proofs"]))
        self._write("forge-receipt.json", receipt)
        with self.assertRaisesRegex(
            UniversalCreationIngressError, "RECEIPT_PROOF_DRIFT"
        ):
            build_universal_creation_proposal(self.root)

    def test_expected_asset_id_binds_consumer_request(self) -> None:
        with self.assertRaisesRegex(
            UniversalCreationIngressError, "CONSUMER_ASSET_ID_MISMATCH"
        ):
            build_universal_creation_proposal(
                self.root, expected_asset_id="other-asset"
            )

    def test_bad_glb_header_is_rejected_even_when_manifest_hash_matches(self) -> None:
        bad = b"not-a-glb-but-hashed"
        (self.root / "lod1.glb").write_bytes(bad)
        manifest = self._load("asset-manifest.json")
        manifest["exports"]["lod1"]["sha256"] = _sha(bad)
        manifest["exports"]["lod1"]["bytes"] = len(bad)
        self._write("asset-manifest.json", manifest)
        with self.assertRaisesRegex(UniversalCreationIngressError, "INVALID_GLB"):
            build_universal_creation_proposal(self.root)

    def test_duplicate_json_keys_are_rejected(self) -> None:
        # Replacing the request with a compact object that repeats asset_id
        # proves duplicate-key rejection before normal schema processing.
        raw = (
            '{"schema":"axm.3d-forge-request/v0.1",'
            '"asset_id":"one","asset_id":"two"}'
        )
        (self.root / "forge-request.json").write_text(raw, encoding="utf-8")
        with self.assertRaisesRegex(
            UniversalCreationIngressError, "DUPLICATE_JSON_KEY"
        ):
            build_universal_creation_proposal(self.root)

    def test_weak_view_distribution_is_hold_not_fake_fail_or_pass(self) -> None:
        manifest = self._load("asset-manifest.json")
        receipt = self._load("forge-receipt.json")
        for index, proof in enumerate(manifest["render_proofs"]):
            proof["angle_degrees"] = index * 10
        receipt["render_proofs"] = manifest["render_proofs"]
        self._write("asset-manifest.json", manifest)
        self._write("forge-receipt.json", receipt)
        proposal = build_universal_creation_proposal(self.root)
        self.assertEqual(
            proposal["review_readiness"]["multi_angle_distribution"]["status"],
            "HOLD",
        )
        self.assertEqual(
            proposal["review_readiness"]["visual_acceptance"], "NOT_GRANTED"
        )

    def test_proposal_write_is_create_only(self) -> None:
        proposal = build_universal_creation_proposal(self.root)
        target = Path(self.temp.name) / "proposal.json"
        write_proposal(target, proposal)
        self.assertTrue(target.is_file())
        with self.assertRaisesRegex(
            UniversalCreationIngressError, "PROPOSAL_EXISTS"
        ):
            write_proposal(target, proposal)


if __name__ == "__main__":
    unittest.main()
