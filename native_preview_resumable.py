#!/usr/bin/env python3
"""Crash-resumable native diagnostic preview evidence.

Adapted from AXM FrameState's checkpoint discipline. A view becomes trusted for
resume only after its exact three diagnostic PNGs and report metadata are
checkpoint-admitted. Tail files produced after the last admitted checkpoint are
discarded and regenerated. Completion assembles the normal preview review surface
and caller-pinned evidence bundle without granting visual or canonical authority.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
import stat
import tempfile
from pathlib import Path
from typing import Any, Iterable

from native_evidence_verify import MANIFEST_SCHEMA, manifest_digest, verify_evidence_bundle
from native_geometry import Mesh
from native_preview import VIEWS, _review_board_html, render
from native_preview_evidence import mesh_digest

CHECKPOINT_SCHEMA = "axm.game-assets.native-preview-checkpoint/v0.1"
RESULT_SCHEMA = "axm.game-assets.native-preview-resumable-result/v0.1"
MAX_VIEWS = 32


class NativePreviewResumeError(ValueError):
    pass


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def _digest(value: Any) -> str:
    return "sha256:" + hashlib.sha256(_canonical(value)).hexdigest()


def _sha256(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _strict_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise NativePreviewResumeError(f"duplicate JSON key: {key}")
        out[key] = value
    return out


def _reject_constant(value: str) -> None:
    raise NativePreviewResumeError(f"non-finite JSON number: {value}")


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent, delete=False
    ) as handle:
        temp = Path(handle.name)
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    try:
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def _real_output_dir(path: Path) -> Path:
    if path.exists():
        try:
            mode = path.lstat().st_mode
        except OSError as exc:
            raise NativePreviewResumeError(f"cannot inspect output directory: {path}") from exc
        if stat.S_ISLNK(mode) or not stat.S_ISDIR(mode):
            raise NativePreviewResumeError("preview output must be a real non-symlink directory")
    else:
        path.mkdir(parents=True, exist_ok=False)
    return path.resolve()


def _identity(mesh: Mesh, size: int, views: tuple[str, ...]) -> dict[str, Any]:
    return {
        "mesh_name": mesh.name,
        "mesh_digest": mesh_digest(mesh),
        "size": [size, size],
        "views": list(views),
        "signals": ["silhouette", "depth", "normal"],
        "renderer": "AXM Game Asset Forge native_preview.py orthographic diagnostic rasterizer",
    }


def _checkpoint_digest(checkpoint: dict[str, Any]) -> str:
    core = copy.deepcopy(checkpoint)
    core.pop("checkpoint_digest", None)
    return _digest(core)


def _load_checkpoint(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        if path.is_symlink() or not path.is_file():
            raise NativePreviewResumeError("render checkpoint must be a regular non-symlink file")
        value = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_strict_pairs,
            parse_constant=_reject_constant,
        )
    except NativePreviewResumeError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise NativePreviewResumeError("render checkpoint is unreadable") from exc
    if not isinstance(value, dict) or value.get("schema") != CHECKPOINT_SCHEMA:
        raise NativePreviewResumeError("unsupported render checkpoint schema")
    if value.get("checkpoint_digest") != _checkpoint_digest(value):
        raise NativePreviewResumeError("render checkpoint digest does not match its content")
    return value


def _regular_file_record(path: Path, root: Path, role: str) -> dict[str, Any]:
    try:
        info = path.lstat()
    except OSError as exc:
        raise NativePreviewResumeError(f"missing admitted preview artifact: {path.name}") from exc
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        raise NativePreviewResumeError(f"preview artifact must be a regular non-symlink file: {path.name}")
    data = path.read_bytes()
    return {
        "path": path.relative_to(root).as_posix(),
        "sha256": _sha256(data),
        "bytes": len(data),
        "role": role,
    }


def _verify_completed(
    root: Path,
    checkpoint: dict[str, Any],
    identity: dict[str, Any],
) -> list[dict[str, Any]]:
    if checkpoint.get("identity") != identity:
        raise NativePreviewResumeError(
            "render checkpoint identity does not match current mesh/size/view request"
        )
    completed = checkpoint.get("completed")
    if not isinstance(completed, list):
        raise NativePreviewResumeError("render checkpoint completed rows are invalid")
    requested_views = identity["views"]
    if len(completed) > len(requested_views):
        raise NativePreviewResumeError("render checkpoint contains too many completed views")

    for index, row in enumerate(completed):
        if not isinstance(row, dict):
            raise NativePreviewResumeError("render checkpoint completed row must be an object")
        if row.get("index") != index or row.get("view") != requested_views[index]:
            raise NativePreviewResumeError("render checkpoint views are not contiguous and ordered")
        report = row.get("report")
        if not isinstance(report, dict) or report.get("view") != requested_views[index]:
            raise NativePreviewResumeError("render checkpoint view report is invalid")
        files = row.get("files")
        if not isinstance(files, list) or len(files) != 3:
            raise NativePreviewResumeError("each admitted view must bind exactly three signal files")
        expected_roles = [
            f"native-preview/{requested_views[index]}/{signal}"
            for signal in ("silhouette", "depth", "normal")
        ]
        for file_index, file_row in enumerate(files):
            if not isinstance(file_row, dict):
                raise NativePreviewResumeError("checkpoint file record must be an object")
            expected_path = f"{requested_views[index]}-{('silhouette','depth','normal')[file_index]}.png"
            if file_row.get("path") != expected_path or file_row.get("role") != expected_roles[file_index]:
                raise NativePreviewResumeError("checkpoint file identity differs from requested view")
            observed = _regular_file_record(root / expected_path, root, expected_roles[file_index])
            if observed != file_row:
                raise NativePreviewResumeError(
                    f"checkpoint-admitted preview artifact differs from receipt: {expected_path}"
                )
    return completed


def _remove_unadmitted(root: Path, views: tuple[str, ...], admitted_count: int) -> list[str]:
    removed: list[str] = []
    for view in views[admitted_count:]:
        for signal in ("silhouette", "depth", "normal"):
            path = root / f"{view}-{signal}.png"
            if path.exists() or path.is_symlink():
                if path.is_dir() and not path.is_symlink():
                    raise NativePreviewResumeError(f"unexpected directory in preview tail: {path.name}")
                path.unlink(missing_ok=True)
                removed.append(path.name)
    for name in (
        "preview-report.json",
        "review.html",
        "evidence-manifest.json",
        "evidence-verification.json",
    ):
        path = root / name
        if path.exists() or path.is_symlink():
            if path.is_dir() and not path.is_symlink():
                raise NativePreviewResumeError(f"unexpected directory in preview finalization path: {name}")
            path.unlink(missing_ok=True)
            removed.append(name)
    return sorted(removed)


def _admit_view(mesh: Mesh, root: Path, view: str, size: int, index: int) -> dict[str, Any]:
    result = render(mesh, view=view, size=size)
    files: list[dict[str, Any]] = []
    for signal in ("silhouette", "depth", "normal"):
        key = f"{signal}_png"
        data = result.pop(key)
        if not isinstance(data, (bytes, bytearray)):
            raise NativePreviewResumeError(f"native preview did not return {key}")
        path = root / f"{view}-{signal}.png"
        _atomic_write(path, bytes(data))
        files.append(
            _regular_file_record(
                path,
                root,
                f"native-preview/{view}/{signal}",
            )
        )
    return {"index": index, "view": view, "report": result, "files": files}


def _assemble_preview(root: Path, mesh: Mesh, completed: list[dict[str, Any]]) -> dict[str, Any]:
    report = {
        "mesh": mesh.name,
        "views": [row["report"] for row in completed],
        "truth": "Aspect-preserving orthographic diagnostic software rasterizer only; not an in-engine acceptance render.",
        "review": {
            "html": "review.html",
            "report": "preview-report.json",
            "authority": "presentation_only_no_automatic_acceptance",
        },
    }
    _atomic_write(
        root / "preview-report.json",
        (json.dumps(report, indent=2, sort_keys=True) + "\n").encode("utf-8"),
    )
    _atomic_write(root / "review.html", _review_board_html(report).encode("utf-8"))
    return report


def _finalize_evidence(
    root: Path,
    identity: dict[str, Any],
    completed: list[dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any]]:
    files = [file_row for row in completed for file_row in row["files"]]
    files.append(_regular_file_record(root / "preview-report.json", root, "native-preview/report"))
    files.append(_regular_file_record(root / "review.html", root, "native-preview/review-surface"))
    manifest: dict[str, Any] = {
        "schema": MANIFEST_SCHEMA,
        "bundle_id": f"native-preview-{identity['mesh_digest'].removeprefix('sha256:')[:20]}",
        "files": files,
        "context": identity,
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
                "exact checkpoint-admitted preview artifact bytes",
                "exact diagnostic mesh digest and declared preview context",
                "completed final evidence was rebuilt only from contiguous admitted views",
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
    _atomic_write(
        root / "evidence-manifest.json",
        (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8"),
    )
    verification = verify_evidence_bundle(
        root,
        root / "evidence-manifest.json",
        expected_manifest_digest=manifest["manifest_digest"],
    )
    _atomic_write(
        root / "evidence-verification.json",
        (json.dumps(verification, indent=2, sort_keys=True) + "\n").encode("utf-8"),
    )
    return manifest, verification


def render_preview_resumable(
    mesh: Mesh,
    output: str | Path,
    *,
    size: int = 128,
    views: Iterable[str] = ("front", "side", "top"),
    max_new_views: int | None = None,
) -> dict[str, Any]:
    if isinstance(size, bool) or not isinstance(size, int) or size < 16:
        raise NativePreviewResumeError("preview size must be an integer >= 16")
    view_tuple = tuple(views)
    if not view_tuple or len(view_tuple) > MAX_VIEWS:
        raise NativePreviewResumeError(f"views must contain between 1 and {MAX_VIEWS} entries")
    if len(set(view_tuple)) != len(view_tuple):
        raise NativePreviewResumeError("preview views must be unique")
    unknown = [view for view in view_tuple if view not in VIEWS]
    if unknown:
        raise NativePreviewResumeError(f"unknown native preview views: {unknown!r}")
    if max_new_views is not None:
        if isinstance(max_new_views, bool) or not isinstance(max_new_views, int) or max_new_views < 0:
            raise NativePreviewResumeError("max_new_views must be a non-negative integer or None")

    root = _real_output_dir(Path(output))
    checkpoint_path = root / "render-checkpoint.json"
    identity = _identity(mesh, size, view_tuple)
    checkpoint = _load_checkpoint(checkpoint_path)

    if checkpoint is None:
        completed: list[dict[str, Any]] = []
        checkpoint = {
            "schema": CHECKPOINT_SCHEMA,
            "identity": identity,
            "completed": completed,
            "status": "IN_PROGRESS",
            "truth_boundary": (
                "only checkpoint-admitted diagnostic view bytes and metadata are trusted for resume; "
                "unadmitted tail artifacts are discarded and regenerated"
            ),
        }
    else:
        completed = _verify_completed(root, checkpoint, identity)

    if checkpoint.get("status") == "COMPLETE" and len(completed) == len(view_tuple):
        manifest_path = root / "evidence-manifest.json"
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            verification = verify_evidence_bundle(
                root,
                manifest_path,
                expected_manifest_digest=manifest["manifest_digest"],
            )
        except Exception as exc:
            raise NativePreviewResumeError(f"completed preview evidence failed re-verification: {exc}") from exc
        return {
            "schema": RESULT_SCHEMA,
            "status": "COMPLETE",
            "completed_views": len(completed),
            "total_views": len(view_tuple),
            "rendered_views_this_run": 0,
            "checkpoint_digest": checkpoint["checkpoint_digest"],
            "evidence_manifest_digest": manifest["manifest_digest"],
            "verification_receipt_digest": verification["receipt_digest"],
            "removed_unadmitted_artifacts": [],
        }

    removed = _remove_unadmitted(root, view_tuple, len(completed))
    budget = None if max_new_views is None else max_new_views
    rendered = 0

    for index in range(len(completed), len(view_tuple)):
        if budget is not None and rendered >= budget:
            break
        row = _admit_view(mesh, root, view_tuple[index], size, index)
        completed.append(row)
        rendered += 1
        checkpoint["completed"] = completed
        checkpoint["status"] = "IN_PROGRESS"
        checkpoint["checkpoint_digest"] = _checkpoint_digest(checkpoint)
        _atomic_write(
            checkpoint_path,
            (json.dumps(checkpoint, indent=2, sort_keys=True) + "\n").encode("utf-8"),
        )

    complete = len(completed) == len(view_tuple)
    if not complete:
        checkpoint["status"] = "PAUSED"
        checkpoint["checkpoint_digest"] = _checkpoint_digest(checkpoint)
        _atomic_write(
            checkpoint_path,
            (json.dumps(checkpoint, indent=2, sort_keys=True) + "\n").encode("utf-8"),
        )
        return {
            "schema": RESULT_SCHEMA,
            "status": "PAUSED",
            "completed_views": len(completed),
            "total_views": len(view_tuple),
            "rendered_views_this_run": rendered,
            "checkpoint_digest": checkpoint["checkpoint_digest"],
            "removed_unadmitted_artifacts": removed,
            "authority": "NONE",
        }

    _assemble_preview(root, mesh, completed)
    manifest, verification = _finalize_evidence(root, identity, completed)
    checkpoint["status"] = "COMPLETE"
    checkpoint["evidence_manifest_digest"] = manifest["manifest_digest"]
    checkpoint["verification_receipt_digest"] = verification["receipt_digest"]
    checkpoint["checkpoint_digest"] = _checkpoint_digest(checkpoint)
    _atomic_write(
        checkpoint_path,
        (json.dumps(checkpoint, indent=2, sort_keys=True) + "\n").encode("utf-8"),
    )
    return {
        "schema": RESULT_SCHEMA,
        "status": "COMPLETE",
        "completed_views": len(completed),
        "total_views": len(view_tuple),
        "rendered_views_this_run": rendered,
        "checkpoint_digest": checkpoint["checkpoint_digest"],
        "evidence_manifest_digest": manifest["manifest_digest"],
        "verification_receipt_digest": verification["receipt_digest"],
        "removed_unadmitted_artifacts": removed,
        "authority": "NONE",
        "truth_boundary": (
            "resumable completion proves contiguous checkpoint-admitted diagnostic preview evidence; "
            "it does not prove visual quality or engine acceptance"
        ),
    }
