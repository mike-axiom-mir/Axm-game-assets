#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from native_geometry import make_box, scale
from native_preview_evidence import write_verified_preview
from native_preview_resumable import NativePreviewResumeError, render_preview_resumable


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _evidence_paths(root: Path) -> list[str]:
    manifest = json.loads((root / "evidence-manifest.json").read_text())
    return [row["path"] for row in manifest["files"]]


def expect_resume_error(fn, text: str) -> None:
    try:
        fn()
    except NativePreviewResumeError as exc:
        assert text in str(exc), str(exc)
    else:
        raise AssertionError(f"expected NativePreviewResumeError containing {text!r}")


def run() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        mesh = make_box((1.2, 0.5, 2.1), name="resumable-preview-box")
        resumed_root = root / "resumed"

        first = render_preview_resumable(
            mesh,
            resumed_root,
            size=48,
            max_new_views=1,
        )
        assert first["status"] == "PAUSED"
        assert first["completed_views"] == 1
        assert first["rendered_views_this_run"] == 1
        assert (resumed_root / "front-silhouette.png").is_file()
        assert not (resumed_root / "side-depth.png").exists()

        # Model a crash after a tail artifact was written but before its view was
        # checkpoint-admitted. Resume must discard this untrusted tail byte body.
        (resumed_root / "side-silhouette.png").write_bytes(b"unadmitted crash tail")
        completed = render_preview_resumable(mesh, resumed_root, size=48)
        assert completed["status"] == "COMPLETE"
        assert completed["completed_views"] == 3
        assert completed["rendered_views_this_run"] == 2
        assert "side-silhouette.png" in completed["removed_unadmitted_artifacts"]
        assert completed["authority"] == "NONE"
        assert (resumed_root / "evidence-manifest.json").is_file()
        assert (resumed_root / "evidence-verification.json").is_file()

        # Resume output must be byte-identical to a clean one-shot preview for
        # every evidence file, not merely visually similar.
        one_shot_root = root / "one-shot"
        one_shot = write_verified_preview(mesh, one_shot_root, size=48)
        assert one_shot["status"] == "PASS"
        resumed_paths = _evidence_paths(resumed_root)
        one_shot_paths = _evidence_paths(one_shot_root)
        assert resumed_paths == one_shot_paths
        assert len(resumed_paths) == 11
        for relative in resumed_paths:
            assert _sha(resumed_root / relative) == _sha(one_shot_root / relative), relative

        # Completed resume is a re-verification, not a rerender.
        repeated = render_preview_resumable(mesh, resumed_root, size=48)
        assert repeated["status"] == "COMPLETE"
        assert repeated["rendered_views_this_run"] == 0
        assert repeated["evidence_manifest_digest"] == completed["evidence_manifest_digest"]

        tamper_root = root / "tamper"
        paused = render_preview_resumable(mesh, tamper_root, size=40, max_new_views=1)
        assert paused["status"] == "PAUSED"
        admitted = tamper_root / "front-depth.png"
        admitted.write_bytes(admitted.read_bytes() + b"tamper")
        expect_resume_error(
            lambda: render_preview_resumable(mesh, tamper_root, size=40),
            "differs from receipt",
        )

        identity_root = root / "identity"
        paused_identity = render_preview_resumable(
            mesh,
            identity_root,
            size=40,
            max_new_views=1,
        )
        assert paused_identity["status"] == "PAUSED"
        expect_resume_error(
            lambda: render_preview_resumable(scale(mesh, 1.1), identity_root, size=40),
            "identity does not match",
        )
        expect_resume_error(
            lambda: render_preview_resumable(mesh, identity_root, size=42),
            "identity does not match",
        )

        checkpoint_root = root / "checkpoint-tamper"
        render_preview_resumable(mesh, checkpoint_root, size=40, max_new_views=1)
        checkpoint_path = checkpoint_root / "render-checkpoint.json"
        checkpoint = json.loads(checkpoint_path.read_text())
        checkpoint["status"] = "COMPLETE"
        checkpoint_path.write_text(json.dumps(checkpoint, indent=2, sort_keys=True) + "\n")
        expect_resume_error(
            lambda: render_preview_resumable(mesh, checkpoint_root, size=40),
            "checkpoint digest",
        )

        zero_root = root / "zero-budget"
        zero = render_preview_resumable(mesh, zero_root, size=32, max_new_views=0)
        assert zero["status"] == "PAUSED"
        assert zero["completed_views"] == 0
        assert zero["rendered_views_this_run"] == 0

        print(
            "NATIVE PREVIEW RESUME TEST PASS",
            completed["completed_views"],
            "views /",
            len(resumed_paths),
            "byte-identical evidence files",
        )


if __name__ == "__main__":
    run()
