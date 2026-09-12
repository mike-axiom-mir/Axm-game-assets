#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from native_evidence_verify import (
    EvidenceVerificationError,
    MANIFEST_SCHEMA,
    manifest_digest,
    verify_evidence_bundle,
)


def sha(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def make_bundle(root: Path, files: dict[str, bytes], bundle_id: str = "fixture") -> tuple[Path, dict]:
    rows = []
    for relative, data in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        rows.append(
            {
                "path": relative,
                "sha256": sha(data),
                "bytes": len(data),
                "role": "fixture",
            }
        )
    manifest = {
        "schema": MANIFEST_SCHEMA,
        "bundle_id": bundle_id,
        "files": rows,
    }
    manifest["manifest_digest"] = manifest_digest(manifest)
    path = root / "evidence-manifest.json"
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path, manifest


class EvidenceVerifyTests(unittest.TestCase):
    def test_exact_bundle_passes(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            manifest_path, manifest = make_bundle(
                root,
                {
                    "proof/front.png": b"not-an-image-but-exact-evidence",
                    "reports/check.json": b'{"status":"pass"}\n',
                },
            )
            receipt = verify_evidence_bundle(
                root,
                manifest_path,
                expected_manifest_digest=manifest["manifest_digest"],
            )
            self.assertEqual(receipt["status"], "PASS")
            self.assertEqual(receipt["summary"]["file_count"], 2)
            self.assertTrue(receipt["receipt_digest"].startswith("sha256:"))
            self.assertFalse(receipt["authority"]["canon"])

    def test_tampered_artifact_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            manifest_path, manifest = make_bundle(root, {"proof.bin": b"original"})
            (root / "proof.bin").write_bytes(b"changed")
            with self.assertRaisesRegex(EvidenceVerificationError, "mismatch"):
                verify_evidence_bundle(
                    root,
                    manifest_path,
                    expected_manifest_digest=manifest["manifest_digest"],
                )

    def test_manifest_content_drift_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            manifest_path, manifest = make_bundle(root, {"proof.bin": b"original"})
            changed = json.loads(manifest_path.read_text(encoding="utf-8"))
            changed["bundle_id"] = "changed"
            manifest_path.write_text(
                json.dumps(changed, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(EvidenceVerificationError, "manifest_digest"):
                verify_evidence_bundle(
                    root,
                    manifest_path,
                    expected_manifest_digest=manifest["manifest_digest"],
                )

    def test_wrong_caller_pin_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            manifest_path, _ = make_bundle(root, {"proof.bin": b"original"})
            with self.assertRaisesRegex(EvidenceVerificationError, "caller expected"):
                verify_evidence_bundle(
                    root,
                    manifest_path,
                    expected_manifest_digest="sha256:" + "0" * 64,
                )

    def test_path_escape_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            outside = root.parent / f"{root.name}-outside.bin"
            outside.write_bytes(b"outside")
            try:
                manifest = {
                    "schema": MANIFEST_SCHEMA,
                    "bundle_id": "escape",
                    "files": [
                        {
                            "path": "../" + outside.name,
                            "sha256": sha(b"outside"),
                            "bytes": len(b"outside"),
                        }
                    ],
                }
                manifest["manifest_digest"] = manifest_digest(manifest)
                manifest_path = root / "evidence-manifest.json"
                manifest_path.write_text(
                    json.dumps(manifest, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8",
                )
                with self.assertRaisesRegex(EvidenceVerificationError, "unsafe"):
                    verify_evidence_bundle(
                        root,
                        manifest_path,
                        expected_manifest_digest=manifest["manifest_digest"],
                    )
            finally:
                outside.unlink(missing_ok=True)

    @unittest.skipUnless(hasattr(os, "symlink"), "symlink unsupported")
    def test_symlink_artifact_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            real = root / "real.bin"
            real.write_bytes(b"same")
            link = root / "link.bin"
            try:
                os.symlink(real.name, link)
            except (OSError, NotImplementedError):
                self.skipTest("symlink creation unavailable")
            manifest = {
                "schema": MANIFEST_SCHEMA,
                "bundle_id": "link",
                "files": [
                    {"path": "link.bin", "sha256": sha(b"same"), "bytes": 4}
                ],
            }
            manifest["manifest_digest"] = manifest_digest(manifest)
            manifest_path = root / "evidence-manifest.json"
            manifest_path.write_text(
                json.dumps(manifest, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(EvidenceVerificationError, "symlink"):
                verify_evidence_bundle(
                    root,
                    manifest_path,
                    expected_manifest_digest=manifest["manifest_digest"],
                )

    def test_duplicate_manifest_path_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "a.bin").write_bytes(b"a")
            manifest = {
                "schema": MANIFEST_SCHEMA,
                "bundle_id": "dup",
                "files": [
                    {"path": "a.bin", "sha256": sha(b"a"), "bytes": 1},
                    {"path": "a.bin", "sha256": sha(b"a"), "bytes": 1},
                ],
            }
            manifest["manifest_digest"] = manifest_digest(manifest)
            manifest_path = root / "evidence-manifest.json"
            manifest_path.write_text(
                json.dumps(manifest, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(EvidenceVerificationError, "duplicate manifest"):
                verify_evidence_bundle(
                    root,
                    manifest_path,
                    expected_manifest_digest=manifest["manifest_digest"],
                )

    def test_duplicate_json_key_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            manifest_path = root / "evidence-manifest.json"
            manifest_path.write_text(
                '{"schema":"axm.game-assets.evidence-bundle/v0.1",'
                '"bundle_id":"a","bundle_id":"b","files":[],"manifest_digest":"sha256:'
                + "0" * 64
                + '"}\n',
                encoding="utf-8",
            )
            with self.assertRaisesRegex(EvidenceVerificationError, "duplicate JSON key"):
                verify_evidence_bundle(
                    root,
                    manifest_path,
                    expected_manifest_digest="sha256:" + "0" * 64,
                )

    def test_cli_receipt_output_is_create_only(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            manifest_path, manifest = make_bundle(root, {"proof.bin": b"original"})
            out = root / "receipt.json"
            script = Path(__file__).resolve().parent / "native_evidence_verify.py"
            args = [
                sys.executable,
                str(script),
                str(root),
                str(manifest_path),
                "--expected-manifest-digest",
                manifest["manifest_digest"],
                "--output",
                str(out),
            ]
            first = subprocess.run(args, capture_output=True, text=True, check=False)
            second = subprocess.run(args, capture_output=True, text=True, check=False)
            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertEqual(second.returncode, 2)
            self.assertIn("already exists", second.stderr)


if __name__ == "__main__":
    unittest.main()
