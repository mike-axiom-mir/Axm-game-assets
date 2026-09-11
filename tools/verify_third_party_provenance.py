#!/usr/bin/env python3
"""Fail-closed verifier for committed third-party provenance claims."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys
from typing import Any

SHA1_RE = re.compile(r"^[0-9a-f]{40}$")
EXPECTED_SCHEMA = "axm-third-party-v1"
MAKEHUMAN_ENTRY_ID = "makehuman-hm08-seed"


class ProvenanceError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def reject(code: str, message: str) -> None:
    raise ProvenanceError(code, message)


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            reject("DUPLICATE_JSON_KEY", f"duplicate JSON key {key!r}")
        out[key] = value
    return out


def read_json(path: Path) -> dict[str, Any]:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        reject("EVIDENCE_READ_FAILED", f"{path}: {exc}")
    try:
        value = json.loads(text, object_pairs_hook=_strict_object)
    except ProvenanceError:
        raise
    except (json.JSONDecodeError, RecursionError) as exc:
        reject("INVALID_JSON", f"{path}: {exc}")
    if not isinstance(value, dict):
        reject("INVALID_DOCUMENT", f"{path}: expected JSON object")
    return value


def safe_file(root: Path, relative: object, *, code: str) -> Path:
    if not isinstance(relative, str) or not relative or "\\" in relative:
        reject(code, f"invalid repository-relative path {relative!r}")
    rel = Path(relative)
    if rel.is_absolute() or ".." in rel.parts or "." in rel.parts:
        reject(code, f"unsafe repository-relative path {relative!r}")
    path = root / rel
    try:
        resolved_root = root.resolve(strict=True)
        resolved = path.resolve(strict=True)
    except OSError as exc:
        reject(code, f"{relative}: {exc}")
    try:
        resolved.relative_to(resolved_root)
    except ValueError:
        reject(code, f"path escapes repository: {relative!r}")
    if path.is_symlink() or not resolved.is_file():
        reject(code, f"expected regular non-symlink file: {relative!r}")
    return resolved


def require_sha1(value: object, label: str) -> str:
    if not isinstance(value, str) or not SHA1_RE.fullmatch(value):
        reject("EVIDENCE_PIN_INVALID", f"{label} must be a lowercase 40-hex Git blob SHA-1")
    return value


def require_text(value: object, label: str, *, code: str = "EVIDENCE_FIELD_INVALID") -> str:
    if not isinstance(value, str) or not value.strip():
        reject(code, f"{label} must be non-empty text")
    return value.strip()


def _get_dict(value: object, label: str, *, code: str = "EVIDENCE_FIELD_INVALID") -> dict[str, Any]:
    if not isinstance(value, dict):
        reject(code, f"{label} must be an object")
    return value


def verify_makehuman_entry(root: Path, entry: dict[str, Any]) -> dict[str, int]:
    provenance = _get_dict(entry.get("provenance"), "provenance", code="PROVENANCE_EVIDENCE_MISSING")
    if entry.get("provenance_required") is not True:
        reject("PROVENANCE_EVIDENCE_MISSING", "verified MakeHuman entry must require provenance")

    asset_license = _get_dict(provenance.get("asset_license"), "provenance.asset_license", code="PROVENANCE_EVIDENCE_MISSING")
    application_license = _get_dict(provenance.get("application_license"), "provenance.application_license", code="PROVENANCE_EVIDENCE_MISSING")
    base_obj = _get_dict(provenance.get("base_obj"), "provenance.base_obj", code="PROVENANCE_EVIDENCE_MISSING")
    pinned_targets = _get_dict(provenance.get("pinned_targets"), "provenance.pinned_targets", code="PROVENANCE_EVIDENCE_MISSING")

    ledger_license = require_text(entry.get("license"), "entry.license")
    evidence_license = require_text(asset_license.get("declared_license"), "provenance.asset_license.declared_license")
    if ledger_license != evidence_license:
        reject("LICENSE_EVIDENCE_MISMATCH", f"ledger license {ledger_license!r} != pinned asset license {evidence_license!r}")

    if entry.get("code_imported") is not False:
        reject("APPLICATION_CODE_BOUNDARY_DRIFT", "MakeHuman application code must remain declared as not imported")

    asset_license_blob = require_sha1(asset_license.get("git_blob_sha1"), "asset license blob")
    application_license_blob = require_sha1(application_license.get("git_blob_sha1"), "application license blob")
    base_obj_blob = require_sha1(base_obj.get("git_blob_sha1"), "base OBJ blob")
    revision = require_sha1(provenance.get("makehuman_revision"), "MakeHuman revision")
    require_text(provenance.get("source_repository"), "provenance.source_repository")
    require_text(provenance.get("captured"), "provenance.captured")

    research_path = safe_file(root, provenance.get("research_record"), code="RESEARCH_RECORD_INVALID")
    try:
        research_text = research_path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        reject("RESEARCH_RECORD_INVALID", str(exc))

    target_pins: dict[str, str] = {}
    evidence_pins = {asset_license_blob, application_license_blob, base_obj_blob}
    for name, raw in pinned_targets.items():
        require_text(name, "pinned target name")
        target = _get_dict(raw, f"pinned target {name}")
        target_pin = require_sha1(target.get("git_blob_sha1"), f"target {name} blob")
        require_text(target.get("path"), f"target {name} path")
        target_pins[name] = target_pin
        evidence_pins.add(target_pin)

    missing_pins = sorted(pin for pin in evidence_pins if pin not in research_text)
    if missing_pins:
        reject("RESEARCH_EVIDENCE_DRIFT", f"research record no longer contains pinned evidence: {', '.join(missing_pins)}")

    listed = provenance.get("seed_manifests")
    if not isinstance(listed, list) or not listed or not all(isinstance(item, str) and item for item in listed):
        reject("SEED_MANIFEST_SET_INVALID", "provenance.seed_manifests must be a non-empty list of paths")
    if len(set(listed)) != len(listed):
        reject("SEED_MANIFEST_SET_INVALID", "provenance.seed_manifests contains duplicates")

    discovered = sorted(
        path.relative_to(root).as_posix()
        for path in root.glob("seed_data/hm08_*/seed-manifest.json")
        if path.is_file() and not path.is_symlink()
    )
    if sorted(listed) != discovered:
        reject(
            "SEED_MANIFEST_SET_DRIFT",
            f"ledger manifests {sorted(listed)!r} != discovered manifests {discovered!r}",
        )

    seen_targets: set[str] = set()
    for relative in listed:
        manifest_path = safe_file(root, relative, code="SEED_MANIFEST_INVALID")
        manifest = read_json(manifest_path)
        source = _get_dict(manifest.get("source"), f"{relative}.source", code="SEED_MANIFEST_INVALID")
        if source.get("makehuman_base_obj_git_blob_sha1") != base_obj_blob:
            reject("BASE_SOURCE_MISMATCH", f"{relative}: MakeHuman base OBJ blob drift")
        if source.get("makehuman_revision") != revision:
            reject("SOURCE_REVISION_MISMATCH", f"{relative}: MakeHuman revision drift")
        license_record = source.get("license_record")
        if not isinstance(license_record, str) or "CC0" not in license_record or "application code" not in license_record:
            reject("SEED_LICENSE_RECORD_INVALID", f"{relative}: source license boundary is missing or ambiguous")

        outputs = _get_dict(manifest.get("outputs"), f"{relative}.outputs", code="SEED_MANIFEST_INVALID")
        targets = outputs.get("targets", [])
        if not isinstance(targets, list):
            reject("SEED_MANIFEST_INVALID", f"{relative}.outputs.targets must be a list")
        for target in targets:
            if not isinstance(target, dict):
                reject("SEED_MANIFEST_INVALID", f"{relative}: target record must be an object")
            name = target.get("name")
            if name in target_pins:
                seen_targets.add(name)
                if target.get("source_git_blob_sha1") != target_pins[name]:
                    reject("TARGET_SOURCE_MISMATCH", f"{relative}: pinned target {name!r} blob drift")

    missing_targets = sorted(set(target_pins) - seen_targets)
    if missing_targets:
        reject("PINNED_TARGET_NOT_OBSERVED", f"pinned target(s) absent from seed manifests: {', '.join(missing_targets)}")

    return {"seed_manifests": len(listed), "pinned_targets": len(target_pins)}


def verify_repository(root: Path) -> dict[str, int]:
    root = root.resolve()
    ledger_path = safe_file(root, "THIRD_PARTY.json", code="LEDGER_INVALID")
    ledger = read_json(ledger_path)
    if ledger.get("schema") != EXPECTED_SCHEMA:
        reject("LEDGER_SCHEMA_INVALID", f"expected {EXPECTED_SCHEMA!r}")
    if ledger.get("repository") != "Axm-game-assets":
        reject("LEDGER_REPOSITORY_MISMATCH", "third-party ledger repository identity drift")

    entries = ledger.get("entries")
    if not isinstance(entries, list):
        reject("LEDGER_INVALID", "entries must be a list")
    by_id: dict[str, dict[str, Any]] = {}
    for item in entries:
        if not isinstance(item, dict):
            reject("LEDGER_INVALID", "each entry must be an object")
        entry_id = require_text(item.get("id"), "entry.id", code="LEDGER_INVALID")
        if entry_id in by_id:
            reject("DUPLICATE_ENTRY_ID", f"duplicate third-party entry {entry_id!r}")
        by_id[entry_id] = item
        if item.get("license_verified") is True and item.get("provenance_required") is not True:
            reject("PROVENANCE_EVIDENCE_MISSING", f"{entry_id}: verified license without required provenance")

    entry = by_id.get(MAKEHUMAN_ENTRY_ID)
    if entry is None:
        reject("MAKEHUMAN_ENTRY_MISSING", f"missing {MAKEHUMAN_ENTRY_ID!r} ledger entry")
    if entry.get("license_verified") is not True:
        reject("LICENSE_VERIFICATION_STATE_DRIFT", "MakeHuman seed entry is no longer marked verified; update the route explicitly instead")
    stats = verify_makehuman_entry(root, entry)
    return {"entries": len(entries), **stats}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args(argv)
    try:
        stats = verify_repository(args.repo_root)
    except ProvenanceError as exc:
        print(f"AXM_PROVENANCE_REJECTED {exc.code}: {exc}", file=sys.stderr)
        return 2
    print("THIRD_PARTY_PROVENANCE_PASS " + json.dumps(stats, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
