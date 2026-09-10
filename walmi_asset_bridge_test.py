#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import struct
import tempfile
import unittest
import zlib

import walmi_asset_bridge as bridge


def png_bytes(width: int = 2, height: int = 2) -> bytes:
    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    raw = b"".join(b"\x00" + b"\x20\x40\x60\xff" * width for _ in range(height))
    return bridge.PNG_SIGNATURE + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b"")


def make_fake_provider(root: Path, *, bad_verify: bool = False, bad_materialize: bool = False, symlink: bool = False) -> Path:
    provider = root / "fake-waldo"
    script = f'''#!/usr/bin/env python3
import hashlib, json, pathlib, sys
cmd = sys.argv[1]
candidate = pathlib.Path(sys.argv[2])
identity = hashlib.sha256(b"provider:" + candidate.read_bytes()).hexdigest()
if cmd == "verify-asset":
    {"print('BROKEN'); raise SystemExit(0)" if bad_verify else "print('OK READY ' + identity); raise SystemExit(0)"}
if cmd == "materialize-asset":
    out = pathlib.Path(sys.argv[3])
    out.mkdir()
    (out / "asset.png").write_bytes({png_bytes()!r})
    (out / "candidate.json").write_text(json.dumps({{"candidate_only": True}}), encoding="utf-8")
    (out / "validation.json").write_text(json.dumps({{"state": "READY"}}), encoding="utf-8")
    {"(out / 'escape').symlink_to(out / 'asset.png')" if symlink else "None"}
    {"print('OK MATERIALIZED ' + ('0' * 64) + ' ' + str(out))" if bad_materialize else "print('OK MATERIALIZED ' + identity + ' ' + str(out))"}
    raise SystemExit(0)
raise SystemExit(2)
'''
    provider.write_text(script, encoding="utf-8")
    provider.chmod(0o755)
    return provider


class WalmiAssetBridgeTest(unittest.TestCase):
    def _candidate(self, root: Path, data: bytes = b"candidate") -> Path:
        path = root / "fixture.axmasset"
        path.write_bytes(data)
        return path

    def test_valid_provider_produces_proposal_only_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            provider = make_fake_provider(root)
            candidate = self._candidate(root)
            proposal = bridge.build_walmi_asset_proposal(provider, candidate, root / "materialized")
            self.assertEqual(proposal["schema"], bridge.SCHEMA)
            self.assertEqual(proposal["status"], "PROPOSAL_ONLY")
            self.assertEqual(proposal["primary_asset"]["width"], 2)
            self.assertEqual(proposal["primary_asset"]["height"], 2)
            self.assertFalse(any(proposal["authority"].values()))
            self.assertEqual(proposal["provider"]["candidate_file_sha256"], hashlib.sha256(b"candidate").hexdigest())
            self.assertEqual([item["path"] for item in proposal["materialized_inventory"]], ["asset.png", "candidate.json", "validation.json"])

    def test_missing_provider_fails_cleanly(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with self.assertRaisesRegex(bridge.BridgeError, "WALMI_PROVIDER_UNAVAILABLE"):
                bridge.build_walmi_asset_proposal(root / "missing", self._candidate(root), root / "out")
            self.assertFalse((root / "out").exists())

    def test_unexpected_verify_protocol_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with self.assertRaisesRegex(bridge.BridgeError, "WALMI_VERIFY_PROTOCOL"):
                bridge.build_walmi_asset_proposal(make_fake_provider(root, bad_verify=True), self._candidate(root), root / "out")

    def test_verify_materialize_identity_drift_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with self.assertRaisesRegex(bridge.BridgeError, "WALMI_IDENTITY_DRIFT"):
                bridge.build_walmi_asset_proposal(make_fake_provider(root, bad_materialize=True), self._candidate(root), root / "out")

    def test_symlinked_materialization_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with self.assertRaisesRegex(bridge.BridgeError, "MATERIALIZATION_UNSAFE"):
                bridge.build_walmi_asset_proposal(make_fake_provider(root, symlink=True), self._candidate(root), root / "out")

    def test_existing_destination_is_never_passed_to_provider(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "out"
            output.mkdir()
            marker = output / "keep"
            marker.write_text("unchanged", encoding="utf-8")
            with self.assertRaisesRegex(bridge.BridgeError, "OUTPUT_EXISTS"):
                bridge.build_walmi_asset_proposal(make_fake_provider(root), self._candidate(root), output)
            self.assertEqual(marker.read_text(encoding="utf-8"), "unchanged")

    def test_integration_record_pins_the_public_provider_contract(self) -> None:
        record = json.loads(Path("integration/walmi-inner-asset-v0.1.json").read_text(encoding="utf-8"))
        self.assertEqual(record["provider"]["repository"], bridge.PROVIDER_REPOSITORY)
        self.assertEqual(record["provider"]["pull_request"], bridge.PROVIDER_PR)
        self.assertEqual(record["provider"]["head"], bridge.PROVIDER_HEAD)
        self.assertEqual(record["consumer"]["proposal_schema"], bridge.SCHEMA)
        self.assertEqual(record["classification"], "OPTIONAL_ADAPTER_BRIDGE")
        self.assertFalse(record["runtime"]["provider_required_for_forge"])
        self.assertFalse(any(record["authority"].values()))

    def test_candidate_file_identity_is_preserved_separately_from_provider_identity(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            provider = make_fake_provider(root)
            a = bridge.build_walmi_asset_proposal(provider, self._candidate(root, b"a"), root / "a-out")
            (root / "fixture.axmasset").unlink()
            b = bridge.build_walmi_asset_proposal(provider, self._candidate(root, b"b"), root / "b-out")
            self.assertNotEqual(a["provider"]["candidate_file_sha256"], b["provider"]["candidate_file_sha256"])
            self.assertNotEqual(a["provider"]["provider_candidate_sha256"], b["provider"]["provider_candidate_sha256"])


if __name__ == "__main__":
    unittest.main()
