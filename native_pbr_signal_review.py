#!/usr/bin/env python3
"""Audit one native_pbr.py material family using the transplanted signal organ.

This adapter is intentionally narrow. It maps semantic map keys declared by the
Game Asset Forge native PBR manifest; it never infers material meaning from
filenames. Packed ORM remains one `unassigned` payload with its packing meaning
preserved separately rather than being misreported as three independent maps.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any

from native_material_signal_audit import (
    MaterialAuditError,
    REQUEST_SCHEMA,
    audit_material_request,
)

REVIEW_SCHEMA = "axm.game-assets.native-pbr-signal-review/v0.1"
SUPPORTED_PBR_SCHEMA = "axm.game-assets.native-pbr.v0.2"
DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
MAP_CHANNELS = {
    "base_color": "base-color",
    "normal": "normal",
    "roughness": "roughness",
    "metallic": "metallic",
    "height": "height",
    "ao": "ambient-occlusion",
    "orm": "unassigned",
}
REQUIRED_MAPS = frozenset(MAP_CHANNELS)


class NativePbrSignalReviewError(ValueError):
    pass


def _strict_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise NativePbrSignalReviewError(f"duplicate JSON key: {key}")
        out[key] = value
    return out


def _load_manifest(path: Path) -> tuple[dict[str, Any], bytes]:
    try:
        raw = path.read_bytes()
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_strict_pairs)
    except NativePbrSignalReviewError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise NativePbrSignalReviewError(f"cannot read native PBR manifest: {exc}") from exc
    if not isinstance(value, dict):
        raise NativePbrSignalReviewError("native PBR manifest must be one JSON object")
    return value, raw


def _sha256(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def build_audit_request(manifest: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    if manifest.get("schema") != SUPPORTED_PBR_SCHEMA:
        raise NativePbrSignalReviewError(
            f"native PBR schema must be {SUPPORTED_PBR_SCHEMA}"
        )
    maps = manifest.get("maps")
    if not isinstance(maps, dict):
        raise NativePbrSignalReviewError("native PBR maps must be an object")
    missing = sorted(REQUIRED_MAPS - set(maps))
    if missing:
        raise NativePbrSignalReviewError(
            "native PBR manifest is missing maps: " + ", ".join(missing)
        )

    entries = []
    for map_id in sorted(REQUIRED_MAPS):
        record = maps.get(map_id)
        if not isinstance(record, dict):
            raise NativePbrSignalReviewError(f"native PBR map {map_id!r} must be an object")
        file_name = record.get("file")
        declared_sha = record.get("sha256")
        if not isinstance(file_name, str) or not file_name:
            raise NativePbrSignalReviewError(f"native PBR map {map_id!r} has no file")
        if not isinstance(declared_sha, str) or not DIGEST_RE.fullmatch(declared_sha):
            raise NativePbrSignalReviewError(
                f"native PBR map {map_id!r} has no valid sha256"
            )
        entries.append(
            {
                "id": map_id,
                "channel": MAP_CHANNELS[map_id],
                "path": file_name,
            }
        )
    held_maps = sorted(set(maps) - REQUIRED_MAPS)
    return {
        "schema": REQUEST_SCHEMA,
        "family_id": f"native-pbr/{manifest.get('kind', 'unknown')}/{manifest.get('seed', 'unknown')}",
        "entries": entries,
    }, held_maps


def review_native_pbr(manifest_path: str | Path) -> dict[str, Any]:
    path = Path(manifest_path).resolve()
    manifest, raw = _load_manifest(path)
    request, held_maps = build_audit_request(manifest)
    try:
        audit = audit_material_request(request, path.parent)
    except MaterialAuditError as exc:
        raise NativePbrSignalReviewError(str(exc)) from exc

    manifest_maps = manifest["maps"]
    mismatches = []
    for row in audit["entries"]:
        map_id = row["id"]
        if row.get("status") == "HOLD":
            continue
        declared = manifest_maps[map_id]["sha256"]
        if row.get("sha256") != declared:
            mismatches.append(
                {
                    "map_id": map_id,
                    "declared_sha256": declared,
                    "observed_sha256": row.get("sha256"),
                }
            )

    status = audit["status"]
    if mismatches:
        status = "HOLD"
    elif held_maps and status == "PASS":
        status = "PASS_WITH_WARNINGS"

    review: dict[str, Any] = {
        "schema": REVIEW_SCHEMA,
        "status": status,
        "native_pbr": {
            "schema": manifest.get("schema"),
            "kind": manifest.get("kind"),
            "seed": manifest.get("seed"),
            "manifest_path": path.name,
            "manifest_file_sha256": _sha256(raw),
        },
        "audit": audit,
        "manifest_hash_mismatches": mismatches,
        "held_unknown_map_keys": held_maps,
        "packed_map_truth": {
            "map_id": "orm",
            "audit_channel": "unassigned",
            "declared_packing": {
                "r": "ambient-occlusion",
                "g": "roughness",
                "b": "metallic",
            },
            "note": (
                "Packed ORM is audited as one payload. This adapter does not pretend "
                "the packed image is three independently materialized channel files."
            ),
        },
        "authority": {
            "canonical_mutation": False,
            "visual_approval": False,
            "automatic_promotion": False,
            "merge": False,
            "canon": False,
        },
        "truth_boundary": {
            "producer_semantics_are_explicit": True,
            "filename_semantics_inferred": False,
            "signal_pass_is_aesthetic_quality": False,
            "signal_pass_is_physical_pbr_certification": False,
        },
    }
    review["review_digest"] = _sha256(
        json.dumps(
            review, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode("utf-8")
    )
    return review


def _write_create_only(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("x", encoding="utf-8", newline="\n") as handle:
            json.dump(value, handle, indent=2, sort_keys=True, ensure_ascii=False)
            handle.write("\n")
    except FileExistsError as exc:
        raise NativePbrSignalReviewError(f"output already exists: {path}") from exc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run the native material signal audit against one native_pbr material.json"
    )
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        review = review_native_pbr(args.manifest)
        if args.output:
            _write_create_only(args.output.resolve(), review)
    except NativePbrSignalReviewError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print(json.dumps(review, sort_keys=True, separators=(",", ":"), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
