#!/usr/bin/env python3
"""Read-only verification for Game Asset evidence bundles.

The stable-file / caller-pin mechanism is adapted from AXM FrameState's
``src/axm_framestate/render_verify.py``. This Game Asset Forge version is a
stdlib-only native port over a generic evidence manifest. It imports no
FrameState code and acquires no merge, visual-approval, release, or CANON
authority.

The verifier exists to answer a narrow question: do the caller-pinned manifest
and every manifest-declared evidence file still have the exact bytes claimed,
without symlink/path escape or an observed change during verification?
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import sys
from typing import Any

MANIFEST_SCHEMA = "axm.game-assets.evidence-bundle/v0.1"
RECEIPT_SCHEMA = "axm.game-assets.evidence-verification/v0.1"
DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
MAX_MANIFEST_BYTES = 16 * 1024 * 1024
MAX_FILES = 4096
MAX_TOTAL_BYTES = 8 * 1024 * 1024 * 1024


class EvidenceVerificationError(ValueError):
    pass


def canonical_json(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def digest_bytes(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def digest_value(value: Any) -> str:
    return digest_bytes(canonical_json(value))


def _strict_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise EvidenceVerificationError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise EvidenceVerificationError(f"non-finite JSON number: {value}")


def _require_digest(value: Any, label: str) -> str:
    if not isinstance(value, str) or not DIGEST_RE.fullmatch(value):
        raise EvidenceVerificationError(f"{label} must be sha256:<64 lowercase hex>")
    return value


def _real_directory(path: Path, label: str) -> Path:
    try:
        info = path.lstat()
    except OSError as exc:
        raise EvidenceVerificationError(f"{label} directory is missing: {path}") from exc
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
        raise EvidenceVerificationError(f"{label} must be a non-symlink directory: {path}")
    return path.resolve()


def _stable_identity(path: Path) -> tuple[int, int, int, int, int]:
    try:
        info = path.lstat()
    except OSError as exc:
        raise EvidenceVerificationError(f"missing evidence file: {path}") from exc
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        raise EvidenceVerificationError(
            f"evidence file must be regular and non-symlink: {path}"
        )
    return (
        info.st_dev,
        info.st_ino,
        info.st_size,
        info.st_mtime_ns,
        info.st_ctime_ns,
    )


def _stat_identity(info: os.stat_result) -> tuple[int, int, int, int, int]:
    return (
        info.st_dev,
        info.st_ino,
        info.st_size,
        info.st_mtime_ns,
        info.st_ctime_ns,
    )


def _confirm_stable(
    path: Path,
    expected: tuple[int, int, int, int, int],
    opened: os.stat_result,
    closed: os.stat_result,
) -> None:
    try:
        after = path.lstat()
    except OSError as exc:
        raise EvidenceVerificationError(
            f"evidence file changed while verifying: {path}"
        ) from exc
    if (
        stat.S_ISLNK(after.st_mode)
        or not stat.S_ISREG(after.st_mode)
        or _stat_identity(opened) != expected
        or _stat_identity(closed) != expected
        or _stat_identity(after) != expected
    ):
        raise EvidenceVerificationError(
            f"evidence file changed while verifying: {path}"
        )


def _read_stable(path: Path, *, limit: int | None = None) -> bytes:
    expected = _stable_identity(path)
    if limit is not None and expected[2] > limit:
        raise EvidenceVerificationError(
            f"evidence file exceeds {limit} byte read limit: {path}"
        )
    try:
        with path.open("rb") as handle:
            opened = os.fstat(handle.fileno())
            data = handle.read() if limit is None else handle.read(limit + 1)
            closed = os.fstat(handle.fileno())
    except OSError as exc:
        raise EvidenceVerificationError(f"cannot read evidence file: {path}") from exc
    if limit is not None and len(data) > limit:
        raise EvidenceVerificationError(
            f"evidence file exceeds {limit} byte read limit: {path}"
        )
    _confirm_stable(path, expected, opened, closed)
    return data


def _hash_stable(path: Path) -> tuple[str, int]:
    expected = _stable_identity(path)
    hashed = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            opened = os.fstat(handle.fileno())
            while True:
                chunk = handle.read(1024 * 1024)
                if not chunk:
                    break
                hashed.update(chunk)
            closed = os.fstat(handle.fileno())
    except OSError as exc:
        raise EvidenceVerificationError(f"cannot hash evidence file: {path}") from exc
    _confirm_stable(path, expected, opened, closed)
    return "sha256:" + hashed.hexdigest(), expected[2]


def _safe_relative(value: Any, label: str) -> PurePosixPath:
    if not isinstance(value, str) or not value or "\\" in value:
        raise EvidenceVerificationError(f"{label} must be one relative POSIX path")
    raw = value.split("/")
    parsed = PurePosixPath(value)
    if (
        parsed.is_absolute()
        or parsed.as_posix() != value
        or any(part in {"", ".", ".."} for part in raw)
    ):
        raise EvidenceVerificationError(f"{label} is unsafe: {value!r}")
    return parsed


def _member_path(root: Path, relative: Any, label: str) -> Path:
    rel = _safe_relative(relative, label)
    current = root
    for part in rel.parts:
        current = current / part
        try:
            if current.is_symlink():
                raise EvidenceVerificationError(
                    f"{label} crosses symlink: {relative!r}"
                )
        except OSError as exc:
            raise EvidenceVerificationError(
                f"cannot inspect {label}: {relative!r}"
            ) from exc
    try:
        current.resolve(strict=True).relative_to(root)
    except (OSError, ValueError) as exc:
        raise EvidenceVerificationError(
            f"{label} escapes or is missing from bundle root: {relative!r}"
        ) from exc
    return current


def _load_manifest(path: Path) -> tuple[dict[str, Any], bytes]:
    raw = _read_stable(path, limit=MAX_MANIFEST_BYTES)
    try:
        text = raw.decode("utf-8", errors="strict")
        value = json.loads(
            text,
            object_pairs_hook=_strict_pairs,
            parse_constant=_reject_constant,
        )
    except EvidenceVerificationError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as exc:
        raise EvidenceVerificationError("manifest is invalid UTF-8 JSON") from exc
    if not isinstance(value, dict):
        raise EvidenceVerificationError("manifest must contain one JSON object")
    return value, raw


def manifest_digest(manifest: dict[str, Any]) -> str:
    core = copy.deepcopy(manifest)
    core.pop("manifest_digest", None)
    return digest_value(core)


def verify_evidence_bundle(
    root: str | Path,
    manifest_path: str | Path,
    *,
    expected_manifest_digest: str,
) -> dict[str, Any]:
    """Verify exact caller-pinned evidence bytes without mutating the bundle."""
    root_path = _real_directory(Path(root), "bundle root")
    manifest_file = Path(manifest_path)
    if not manifest_file.is_absolute():
        manifest_file = root_path / manifest_file
    try:
        manifest_file.resolve(strict=True).relative_to(root_path)
    except (OSError, ValueError) as exc:
        raise EvidenceVerificationError(
            "manifest must be an existing file inside bundle root"
        ) from exc
    for parent in [manifest_file, *manifest_file.parents]:
        if parent == root_path:
            break
        if parent.is_symlink():
            raise EvidenceVerificationError("manifest path crosses symlink")
    manifest, manifest_bytes = _load_manifest(manifest_file)

    if manifest.get("schema") != MANIFEST_SCHEMA:
        raise EvidenceVerificationError(
            f"manifest schema must be {MANIFEST_SCHEMA}"
        )
    bundle_id = manifest.get("bundle_id")
    if not isinstance(bundle_id, str) or not bundle_id.strip():
        raise EvidenceVerificationError("manifest bundle_id must be non-empty")
    recorded = _require_digest(
        manifest.get("manifest_digest"), "manifest manifest_digest"
    )
    calculated = manifest_digest(manifest)
    if recorded != calculated:
        raise EvidenceVerificationError(
            "manifest_digest does not match manifest content"
        )
    caller_pin = _require_digest(
        expected_manifest_digest, "caller expected manifest digest"
    )
    if caller_pin != recorded:
        raise EvidenceVerificationError(
            "caller expected manifest digest does not match bundle"
        )

    files = manifest.get("files")
    if not isinstance(files, list) or not files:
        raise EvidenceVerificationError("manifest files must be a non-empty list")
    if len(files) > MAX_FILES:
        raise EvidenceVerificationError(
            f"manifest declares more than {MAX_FILES} files"
        )

    seen: set[str] = set()
    observed: list[dict[str, Any]] = []
    total = 0
    for index, entry in enumerate(files):
        if not isinstance(entry, dict):
            raise EvidenceVerificationError(
                f"manifest files[{index}] must be an object"
            )
        relative = entry.get("path")
        parsed = _safe_relative(relative, f"files[{index}].path")
        normalized = parsed.as_posix()
        if normalized in seen:
            raise EvidenceVerificationError(
                f"duplicate manifest file path: {normalized}"
            )
        seen.add(normalized)
        expected_sha = _require_digest(
            entry.get("sha256"), f"files[{index}].sha256"
        )
        declared_bytes = entry.get("bytes")
        if (
            not isinstance(declared_bytes, int)
            or isinstance(declared_bytes, bool)
            or declared_bytes < 0
        ):
            raise EvidenceVerificationError(
                f"files[{index}].bytes must be a nonnegative integer"
            )
        path = _member_path(root_path, normalized, f"files[{index}].path")
        actual_sha, actual_bytes = _hash_stable(path)
        total += actual_bytes
        if total > MAX_TOTAL_BYTES:
            raise EvidenceVerificationError(
                f"bundle exceeds {MAX_TOTAL_BYTES} verified-byte budget"
            )
        if actual_bytes != declared_bytes:
            raise EvidenceVerificationError(
                f"byte count mismatch for {normalized}"
            )
        if actual_sha != expected_sha:
            raise EvidenceVerificationError(
                f"SHA-256 mismatch for {normalized}"
            )
        observed.append(
            {
                "path": normalized,
                "sha256": actual_sha,
                "bytes": actual_bytes,
                "role": entry.get("role"),
            }
        )

    receipt: dict[str, Any] = {
        "schema": RECEIPT_SCHEMA,
        "status": "PASS",
        "bundle_id": bundle_id,
        "manifest": {
            "path": manifest_file.relative_to(root_path).as_posix(),
            "sha256": digest_bytes(manifest_bytes),
            "manifest_digest": recorded,
        },
        "files": observed,
        "summary": {
            "file_count": len(observed),
            "verified_bytes": total,
        },
        "authority": {
            "visual_approval": False,
            "canonical_mutation": False,
            "automatic_install": False,
            "release": False,
            "merge": False,
            "canon": False,
        },
        "truth_boundary": {
            "proves": [
                "the caller-pinned manifest content identity",
                "the exact SHA-256 and byte length of every manifest-declared file at verification time",
                "the checked paths were non-symlink regular files inside the bundle root",
            ],
            "does_not_prove": [
                "visual quality",
                "semantic correctness",
                "engine compatibility",
                "authorship or license fitness",
                "that evidence was produced by the claimed tool merely because a manifest says so",
            ],
        },
        "provenance": {
            "mechanism_source": (
                "mike-axiom-mir/axm-framestate "
                "src/axm_framestate/render_verify.py"
            ),
            "implementation": "AXM Game Asset Forge native genericized Python port",
        },
    }
    receipt["receipt_digest"] = digest_value(receipt)
    return receipt


def _write_create_only(path: Path, receipt: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("x", encoding="utf-8", newline="\n") as handle:
            json.dump(receipt, handle, indent=2, sort_keys=True, ensure_ascii=False)
            handle.write("\n")
    except FileExistsError as exc:
        raise EvidenceVerificationError(f"output already exists: {path}") from exc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Verify one caller-pinned Game Asset evidence bundle"
    )
    parser.add_argument("root", type=Path)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--expected-manifest-digest", required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        receipt = verify_evidence_bundle(
            args.root,
            args.manifest,
            expected_manifest_digest=args.expected_manifest_digest,
        )
        if args.output:
            _write_create_only(args.output.resolve(), receipt)
    except EvidenceVerificationError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print(json.dumps(receipt, sort_keys=True, separators=(",", ":"), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
