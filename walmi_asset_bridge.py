#!/usr/bin/env python3
"""Optional, proposal-only bridge from a verified WALMI .axmasset candidate.

The bridge deliberately depends only on WALMI's public CLI contract. It never
imports WALMI source, discovers a provider implicitly, or mutates Game Asset
Genome state. A caller must name the provider executable and output locations.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import struct
import subprocess
import sys
from typing import Any, Iterable

SCHEMA = "axm.game-assets.walmi-asset-proposal/v0.1"
PROVIDER_REPOSITORY = "mike-axiom-mir/axm-walmi"
PROVIDER_PR = 7
PROVIDER_HEAD = "abe3fd43c588ff2a282298b27e4c0530f8d88fc2"
PROVIDER_CONTRACT = "waldo-axm-mirror verify-asset+materialize-asset"
MAX_CANDIDATE_BYTES = 64 * 1024 * 1024
MAX_MATERIALIZED_FILES = 128
MAX_MATERIALIZED_BYTES = 64 * 1024 * 1024
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


class BridgeError(RuntimeError):
    def __init__(self, code: str, detail: str):
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


def _strict_object_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise BridgeError("DUPLICATE_JSON_KEY", key)
        result[key] = value
    return result


def _read_json_object(path: Path) -> dict[str, Any]:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise BridgeError("JSON_READ_FAILED", f"{path.name}: {exc}") from exc
    try:
        value = json.loads(text, object_pairs_hook=_strict_object_pairs)
    except BridgeError:
        raise
    except json.JSONDecodeError as exc:
        raise BridgeError("INVALID_JSON", f"{path.name}: {exc}") from exc
    if not isinstance(value, dict):
        raise BridgeError("JSON_NOT_OBJECT", path.name)
    return value


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _require_regular_file(path: Path, *, code: str, max_bytes: int | None = None) -> os.stat_result:
    try:
        info = path.lstat()
    except OSError as exc:
        raise BridgeError(code, f"cannot inspect {path}: {exc}") from exc
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        raise BridgeError(code, f"not a regular file: {path}")
    if max_bytes is not None and info.st_size > max_bytes:
        raise BridgeError(code, f"file exceeds {max_bytes} bytes: {path}")
    return info


def _provider_call(provider: Path, args: Iterable[str]) -> str:
    _require_regular_file(provider, code="WALMI_PROVIDER_UNAVAILABLE")
    command = [str(provider), *args]
    try:
        completed = subprocess.run(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="strict",
            timeout=60,
            check=False,
        )
    except (OSError, subprocess.SubprocessError, UnicodeError) as exc:
        raise BridgeError("WALMI_PROVIDER_FAILED", str(exc)) from exc
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip() or f"exit {completed.returncode}"
        raise BridgeError("WALMI_PROVIDER_REJECTED", detail)
    return completed.stdout.strip()


def _parse_verify(stdout: str) -> str:
    parts = stdout.split()
    if len(parts) != 3 or parts[0:2] != ["OK", "READY"]:
        raise BridgeError("WALMI_VERIFY_PROTOCOL", f"unexpected output: {stdout!r}")
    digest = parts[2].lower()
    if len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
        raise BridgeError("WALMI_VERIFY_PROTOCOL", "candidate identity is not SHA-256 shaped")
    return digest


def _parse_materialize(stdout: str, expected_destination: Path) -> str:
    parts = stdout.split(maxsplit=3)
    if len(parts) != 4 or parts[0:2] != ["OK", "MATERIALIZED"]:
        raise BridgeError("WALMI_MATERIALIZE_PROTOCOL", f"unexpected output: {stdout!r}")
    digest = parts[2].lower()
    if len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
        raise BridgeError("WALMI_MATERIALIZE_PROTOCOL", "candidate identity is not SHA-256 shaped")
    if Path(parts[3]).resolve() != expected_destination.resolve():
        raise BridgeError("WALMI_MATERIALIZE_PROTOCOL", "provider reported a different destination")
    return digest


def _materialized_inventory(root: Path) -> list[dict[str, Any]]:
    try:
        root_info = root.lstat()
    except OSError as exc:
        raise BridgeError("MATERIALIZATION_MISSING", str(exc)) from exc
    if stat.S_ISLNK(root_info.st_mode) or not stat.S_ISDIR(root_info.st_mode):
        raise BridgeError("MATERIALIZATION_UNSAFE", "materialized root is not a real directory")

    inventory: list[dict[str, Any]] = []
    total_bytes = 0
    for current, dirs, files in os.walk(root, topdown=True, followlinks=False):
        current_path = Path(current)
        for name in dirs:
            directory = current_path / name
            info = directory.lstat()
            if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
                raise BridgeError("MATERIALIZATION_UNSAFE", f"unsafe directory entry: {directory}")
        for name in files:
            path = current_path / name
            info = _require_regular_file(path, code="MATERIALIZATION_UNSAFE")
            relative = path.relative_to(root).as_posix()
            if relative.startswith("/") or ".." in Path(relative).parts:
                raise BridgeError("MATERIALIZATION_UNSAFE", f"unsafe relative path: {relative}")
            total_bytes += info.st_size
            if total_bytes > MAX_MATERIALIZED_BYTES:
                raise BridgeError("MATERIALIZATION_TOO_LARGE", f"exceeds {MAX_MATERIALIZED_BYTES} bytes")
            inventory.append({"path": relative, "bytes": info.st_size, "sha256": _sha256(path)})
            if len(inventory) > MAX_MATERIALIZED_FILES:
                raise BridgeError("MATERIALIZATION_TOO_MANY_FILES", f"exceeds {MAX_MATERIALIZED_FILES} files")
    inventory.sort(key=lambda item: item["path"].encode("utf-8"))
    return inventory


def _png_identity(path: Path) -> dict[str, Any]:
    _require_regular_file(path, code="PRIMARY_ASSET_INVALID")
    try:
        with path.open("rb") as handle:
            header = handle.read(24)
    except OSError as exc:
        raise BridgeError("PRIMARY_ASSET_INVALID", str(exc)) from exc
    if len(header) != 24 or header[:8] != PNG_SIGNATURE or header[12:16] != b"IHDR":
        raise BridgeError("PRIMARY_ASSET_INVALID", "asset.png is not a PNG with an IHDR header")
    width, height = struct.unpack(">II", header[16:24])
    if width == 0 or height == 0 or width > 16384 or height > 16384:
        raise BridgeError("PRIMARY_ASSET_INVALID", f"unsupported PNG dimensions {width}x{height}")
    return {"width": width, "height": height, "sha256": _sha256(path), "bytes": path.stat().st_size}


def build_walmi_asset_proposal(provider: Path, candidate: Path, materialized: Path) -> dict[str, Any]:
    provider = provider.resolve()
    candidate = candidate.resolve()
    materialized = materialized.resolve()
    _require_regular_file(candidate, code="CANDIDATE_INVALID", max_bytes=MAX_CANDIDATE_BYTES)
    if materialized.exists() or materialized.is_symlink():
        raise BridgeError("OUTPUT_EXISTS", f"materialized destination already exists: {materialized}")
    if not materialized.parent.is_dir():
        raise BridgeError("OUTPUT_PARENT_MISSING", str(materialized.parent))

    candidate_file_sha256 = _sha256(candidate)
    verify_identity = _parse_verify(_provider_call(provider, ["verify-asset", str(candidate)]))
    materialize_identity = _parse_materialize(
        _provider_call(provider, ["materialize-asset", str(candidate), str(materialized)]), materialized
    )
    if materialize_identity != verify_identity:
        raise BridgeError("WALMI_IDENTITY_DRIFT", "verify and materialize reported different candidate identities")

    inventory = _materialized_inventory(materialized)
    by_path = {item["path"]: item for item in inventory}
    for required in ("asset.png", "candidate.json", "validation.json"):
        if required not in by_path:
            raise BridgeError("MATERIALIZATION_INCOMPLETE", f"missing {required}")
    _read_json_object(materialized / "candidate.json")
    _read_json_object(materialized / "validation.json")
    primary = _png_identity(materialized / "asset.png")

    return {
        "schema": SCHEMA,
        "status": "PROPOSAL_ONLY",
        "provider": {
            "repository": PROVIDER_REPOSITORY,
            "pull_request": PROVIDER_PR,
            "head": PROVIDER_HEAD,
            "contract": PROVIDER_CONTRACT,
            "candidate_file_sha256": candidate_file_sha256,
            "provider_candidate_sha256": verify_identity,
        },
        "consumer": {
            "repository": "mike-axiom-mir/Axm-game-assets",
            "role": "external_visual_candidate",
        },
        "primary_asset": {"path": "asset.png", **primary},
        "materialized_inventory": inventory,
        "authority": {
            "automatic_install": False,
            "automatic_selection": False,
            "visual_approval": False,
            "genome_mutation": False,
            "promotion": False,
            "merge": False,
            "canon": False,
        },
        "truth_boundary": {
            "provider_verification": "WALMI verified and deterministically materialized the candidate before consumer admission",
            "consumer_verification": "Game Assets independently inventories materialized regular files and validates the primary PNG boundary",
            "not_proven": [
                "visual quality",
                "authorship",
                "license fitness",
                "game compatibility",
                "engine readiness",
                "CANON",
            ],
        },
    }


def _write_new_json(path: Path, value: dict[str, Any]) -> None:
    if path.exists() or path.is_symlink():
        raise BridgeError("PROPOSAL_EXISTS", str(path))
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    try:
        with path.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(payload)
    except OSError as exc:
        raise BridgeError("PROPOSAL_WRITE_FAILED", str(exc)) from exc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Admit a WALMI .axmasset as a proposal-only Game Assets external visual candidate")
    parser.add_argument("--provider", required=True, type=Path, help="explicit waldo-axm-mirror executable path")
    parser.add_argument("--candidate", required=True, type=Path, help="verified .axmasset candidate path")
    parser.add_argument("--materialized", required=True, type=Path, help="new directory for WALMI materialization")
    parser.add_argument("--proposal", required=True, type=Path, help="new JSON proposal receipt path")
    args = parser.parse_args(argv)
    try:
        proposal = build_walmi_asset_proposal(args.provider, args.candidate, args.materialized)
        _write_new_json(args.proposal, proposal)
    except BridgeError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print(json.dumps(proposal, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
