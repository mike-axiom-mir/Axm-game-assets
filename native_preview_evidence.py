#!/usr/bin/env python3
"""Build and caller-pin one native diagnostic preview evidence bundle.

This module wires the native software preview path to the caller-pinned evidence
verifier transplanted from FrameState. It proves exact diagnostic bytes and
context, not visual quality or engine acceptance.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Iterable

from native_evidence_verify import (
    EvidenceVerificationError,
    MANIFEST_SCHEMA,
    manifest_digest,
    verify_evidence_bundle,
)
from native_geometry import Mesh
from native_preview import write_preview

SCHEMA = "axm.game-assets.native-preview-evidence/v0.1"


class NativePreviewEvidenceError(ValueError):
    pass


def _sha256(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def mesh_digest(mesh: Mesh) -> str:
    payload = {
        "name": mesh.name,
        "vertices": [list(vertex) for vertex in mesh.vertices],
        "faces": [list(face) for face in mesh.faces],
    }
    return _sha256(_canonical(payload))


def _record(path: Path, root: Path, role: str) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise NativePreviewEvidenceError(f"preview evidence must be a regular file: {path}")
    data = path.read_bytes()
    return {
        "path": path.relative_to(root).as_posix(),
        "sha256": _sha256(data),
        "bytes": len(data),
        "role": role,
    }


def _write_create_only(path: Path, value: dict[str, Any]) -> None:
    try:
        with path.open("x", encoding="utf-8", newline="\n") as handle:
            json.dump(value, handle, indent=2, sort_keys=True, ensure_ascii=False)
            handle.write("\n")
    except FileExistsError as exc:
        raise NativePreviewEvidenceError(f"output already exists: {path}") from exc


def write_verified_preview(
    mesh: Mesh,
    output: str | Path,
    *,
    size: int = 128,
    views: Iterable[str] = ("front", "side", "top"),
) -> dict[str, Any]:
    root = Path(output).resolve()
    try:
        root.mkdir(parents=True, exist_ok=False)
    except FileExistsError as exc:
        raise NativePreviewEvidenceError(f"preview evidence output already exists: {root}") from exc

    view_list = tuple(views)
    if not view_list:
        raise NativePreviewEvidenceError("at least one preview view is required")

    try:
        preview = write_preview(mesh, root, size=size, views=view_list)
    except Exception as exc:
        raise NativePreviewEvidenceError(f"native preview generation failed: {exc}") from exc

    files: list[dict[str, Any]] = []
    for view in view_list:
        for signal in ("silhouette", "depth", "normal"):
            files.append(
                _record(
                    root / f"{view}-{signal}.png",
                    root,
                    f"native-preview/{view}/{signal}",
                )
            )
    files.append(_record(root / "preview-report.json", root, "native-preview/report"))
    files.append(_record(root / "review.html", root, "native-preview/review-surface"))

    source_digest = mesh_digest(mesh)
    bundle_id = f"native-preview-{source_digest.removeprefix('sha256:')[:20]}"
    manifest: dict[str, Any] = {
        "schema": MANIFEST_SCHEMA,
        "bundle_id": bundle_id,
        "files": files,
        "context": {
            "producer": "AXM Game Asset Forge native_preview.py",
            "wrapper_schema": SCHEMA,
            "mesh_name": mesh.name,
            "mesh_digest": source_digest,
            "size": [size, size],
            "views": list(view_list),
            "signals": ["silhouette", "depth", "normal"],
            "projection": "orthographic diagnostic software rasterizer",
        },
        "authority": {
            "visual_approval": False,
            "engine_acceptance": False,
            "canonical_mutation": False,
            "release": False,
            "merge": False,
            "canon": False,
        },
        "truth_boundary": {
            "proves_after_verification": [
                "exact caller-pinned preview artifact bytes",
                "exact diagnostic mesh digest and declared preview context",
            ],
            "does_not_prove": [
                "aesthetic quality",
                "engine rendering parity",
                "gameplay readability",
                "AAA quality",
                "canonical acceptance",
            ],
        },
    }
    manifest["manifest_digest"] = manifest_digest(manifest)
    manifest_path = root / "evidence-manifest.json"
    _write_create_only(manifest_path, manifest)

    try:
        verification = verify_evidence_bundle(
            root,
            manifest_path,
            expected_manifest_digest=manifest["manifest_digest"],
        )
    except EvidenceVerificationError as exc:
        raise NativePreviewEvidenceError(
            f"fresh preview evidence did not verify: {exc}"
        ) from exc
    _write_create_only(root / "evidence-verification.json", verification)

    result: dict[str, Any] = {
        "schema": SCHEMA,
        "status": verification["status"],
        "mesh_digest": source_digest,
        "preview": preview,
        "evidence_manifest_digest": manifest["manifest_digest"],
        "verification_receipt_digest": verification["receipt_digest"],
        "evidence_file_count": verification["summary"]["file_count"],
        "authority": manifest["authority"],
        "truth_boundary": manifest["truth_boundary"],
    }
    result["result_digest"] = _sha256(_canonical(result))
    return result
