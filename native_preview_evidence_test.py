#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory

from native_evidence_verify import EvidenceVerificationError, verify_evidence_bundle
from native_geometry import make_box, scale
from native_preview_evidence import (
    NativePreviewEvidenceError,
    mesh_digest,
    write_verified_preview,
)


def run() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        mesh = make_box((1.0, 0.5, 2.0), name="preview-evidence-box")

        result = write_verified_preview(mesh, root / "bundle", size=48)
        assert result["status"] == "PASS"
        assert result["evidence_file_count"] == 11
        assert result["authority"]["canon"] is False
        assert result["authority"]["engine_acceptance"] is False
        assert result["mesh_digest"] == mesh_digest(mesh)
        assert result["mesh_digest"] != mesh_digest(scale(mesh, 2.0))

        bundle = root / "bundle"
        manifest = json.loads((bundle / "evidence-manifest.json").read_text())
        verified = verify_evidence_bundle(
            bundle,
            "evidence-manifest.json",
            expected_manifest_digest=manifest["manifest_digest"],
        )
        assert verified["status"] == "PASS"
        assert verified["summary"]["file_count"] == 11

        tampered = bundle / "front-silhouette.png"
        tampered.write_bytes(tampered.read_bytes() + b"tamper")
        try:
            verify_evidence_bundle(
                bundle,
                "evidence-manifest.json",
                expected_manifest_digest=manifest["manifest_digest"],
            )
        except EvidenceVerificationError as exc:
            assert "byte count mismatch" in str(exc) or "SHA-256 mismatch" in str(exc)
        else:
            raise AssertionError("expected tampered preview rejection")

        try:
            write_verified_preview(mesh, bundle, size=48)
        except NativePreviewEvidenceError as exc:
            assert "already exists" in str(exc)
        else:
            raise AssertionError("expected create-only output rejection")

        print(
            "NATIVE PREVIEW EVIDENCE TEST PASS",
            result["evidence_file_count"],
            "caller-pinned files",
        )


if __name__ == "__main__":
    run()
