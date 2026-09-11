#!/usr/bin/env python3
"""Read-only human recovery surface for Forge initialization HOLD states.

This tool never repairs, removes, archives, initializes, or mutates Game Asset
Genome state. It explains what is already present so a human can choose the
next action without guessing after AXM_FORGE_INIT_OUTPUT_EXISTS.
"""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
from typing import Any

import forge

SCHEMA = "axm.forge-init-inspection/v0.1"
MAX_INSPECT_BYTES = 64 * 1024 * 1024


class InspectionError(ValueError):
    """Raised when existing initialization evidence is ambiguous."""


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise InspectionError(f"duplicate JSON member: {key}")
        result[key] = value
    return result


def _read_json_regular(path: Path) -> dict[str, Any]:
    if path.is_symlink():
        raise InspectionError(f"refusing symlinked initialization evidence: {path.name}")
    try:
        stat = path.stat()
    except OSError as error:
        raise InspectionError(f"cannot inspect {path.name}: {error}") from error
    if not path.is_file():
        raise InspectionError(f"initialization evidence is not a regular file: {path.name}")
    if stat.st_size > MAX_INSPECT_BYTES:
        raise InspectionError(
            f"{path.name} exceeds the {MAX_INSPECT_BYTES}-byte read-only inspection ceiling"
        )
    try:
        text = path.read_text(encoding="utf-8")
        value = json.loads(text, object_pairs_hook=_strict_object)
    except (OSError, UnicodeError, json.JSONDecodeError, InspectionError) as error:
        if isinstance(error, InspectionError):
            raise
        raise InspectionError(f"cannot admit {path.name} as strict UTF-8 JSON: {error}") from error
    if not isinstance(value, dict):
        raise InspectionError(f"{path.name} must contain one JSON object")
    return value


def _embedded_digest_matches(value: dict[str, Any], field: str) -> bool:
    observed = value.get(field)
    if not isinstance(observed, str) or not observed:
        return False
    payload = copy.deepcopy(value)
    payload.pop(field, None)
    return forge.digest(payload) == observed


def _report(
    output: Path,
    state: str,
    why: str,
    safe_to_initialize_here: bool,
    facts: dict[str, Any],
    next_actions: list[str],
) -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "output": str(output),
        "state": state,
        "why": why,
        "safe_to_initialize_here": safe_to_initialize_here,
        "facts": facts,
        "next_actions": next_actions,
        "authority": {
            "read_only": True,
            "automatic_repair": False,
            "automatic_delete": False,
            "automatic_archive": False,
            "initialization": False,
            "canonical_state_mutation": False,
            "promotion": False,
            "canon": False,
        },
    }


def inspect_init_output(output: str | Path) -> dict[str, Any]:
    """Classify an init output without changing any existing byte."""
    out = Path(output)
    base_facts = {
        "output_exists": out.exists() or out.is_symlink(),
        "genome_present": False,
        "intake_receipt_present": False,
    }

    if not base_facts["output_exists"]:
        return _report(
            out,
            "AVAILABLE",
            "No filesystem entry currently occupies this output path.",
            True,
            base_facts,
            [
                "Choose the intended request and run forge.py init against this path.",
                "Treat create-only initialization as the final admission check because another process may still win the path first.",
            ],
        )

    if out.is_symlink():
        return _report(
            out,
            "HELD_SYMLINKED_OUTPUT",
            "The requested output path is a symbolic link, so this inspector will not treat its target as Forge authority.",
            False,
            base_facts,
            [
                "Preserve the link until you have reviewed why it exists.",
                "Choose a different unused output path, or explicitly resolve/archive the link outside this read-only tool.",
            ],
        )

    if not out.is_dir():
        return _report(
            out,
            "HELD_NOT_DIRECTORY",
            "The output path is occupied by a non-directory filesystem entry.",
            False,
            base_facts,
            [
                "Do not overwrite this entry automatically.",
                "Choose another output path, or explicitly archive/remove the existing entry after human review.",
            ],
        )

    genome_path = out / "genome.json"
    receipt_path = out / "receipts" / "000-intake.json"
    genome_present = genome_path.exists() or genome_path.is_symlink()
    receipt_present = receipt_path.exists() or receipt_path.is_symlink()
    facts = {
        **base_facts,
        "genome_present": genome_present,
        "intake_receipt_present": receipt_present,
    }

    if not genome_present and not receipt_present:
        return _report(
            out,
            "HELD_OCCUPIED",
            "The directory exists but does not expose either canonical initialization evidence file.",
            False,
            facts,
            [
                "Do not infer that the directory is disposable or a failed Forge run.",
                "Choose another output path, or inspect/archive this directory explicitly outside this read-only tool.",
            ],
        )

    if genome_present != receipt_present:
        missing = "receipts/000-intake.json" if genome_present else "genome.json"
        return _report(
            out,
            "HELD_PARTIAL_INITIALIZATION",
            f"Only one initialization evidence file is present; {missing} is missing. This is compatible with an interrupted create-only initialization but does not prove the cause.",
            False,
            facts,
            [
                "Preserve the partial directory; this tool will not complete or delete it.",
                "Choose a new output path for immediate work, or perform an explicit recovery/archive decision after reviewing the retained bytes.",
            ],
        )

    try:
        genome = _read_json_regular(genome_path)
        intake = _read_json_regular(receipt_path)
    except InspectionError as error:
        return _report(
            out,
            "HELD_AMBIGUOUS_INITIALIZATION",
            str(error),
            False,
            facts,
            [
                "Preserve the existing bytes; automatic repair would invent authority.",
                "Choose a new output path, or perform explicit recovery/archive review outside this read-only tool.",
            ],
        )

    genome_digest_valid = _embedded_digest_matches(genome, "genome_digest")
    receipt_digest_valid = _embedded_digest_matches(intake, "receipt_digest")
    request_digest = genome.get("provenance", {}).get("request_digest") if isinstance(genome.get("provenance"), dict) else None
    receipt_inputs = intake.get("inputs")
    receipt_outputs = intake.get("outputs")
    request_bound = isinstance(request_digest, str) and isinstance(receipt_inputs, list) and request_digest in receipt_inputs
    intake_shape_valid = intake.get("stage") == "intake" and intake.get("status") == "pass"
    current_genome_is_intake_output = (
        isinstance(receipt_outputs, list)
        and isinstance(genome.get("genome_digest"), str)
        and genome["genome_digest"] in receipt_outputs
    )
    facts.update(
        {
            "genome_digest_valid": genome_digest_valid,
            "intake_receipt_digest_valid": receipt_digest_valid,
            "intake_stage_pass": intake_shape_valid,
            "request_digest_bound_to_intake": request_bound,
            "current_genome_is_intake_output": current_genome_is_intake_output,
            "asset_id": genome.get("asset", {}).get("id") if isinstance(genome.get("asset"), dict) else None,
        }
    )

    if not all((genome_digest_valid, receipt_digest_valid, request_bound, intake_shape_valid)):
        failed = [
            name
            for name, ok in (
                ("Genome self-digest", genome_digest_valid),
                ("intake receipt self-digest", receipt_digest_valid),
                ("request-to-intake binding", request_bound),
                ("intake stage/status", intake_shape_valid),
            )
            if not ok
        ]
        return _report(
            out,
            "HELD_AMBIGUOUS_INITIALIZATION",
            "Existing Forge-looking files failed read-only admission: " + ", ".join(failed) + ".",
            False,
            facts,
            [
                "Preserve the existing bytes and investigate the failed identity checks.",
                "Use a different output path unless and until a human deliberately resolves this state.",
            ],
        )

    if current_genome_is_intake_output:
        return _report(
            out,
            "ESTABLISHED_INITIALIZATION",
            "Genome and intake receipt are self-consistent and the current Genome is the exact output recorded by intake.",
            False,
            facts,
            [
                f"Reuse this established asset intentionally; audit it with: python forge.py audit {genome_path}",
                "Choose a different output path if you intended to initialize a separate asset body.",
            ],
        )

    return _report(
        out,
        "ESTABLISHED_FORGE_STATE",
        "Genome and intake receipt remain individually valid and share request identity, but the current Genome no longer equals the intake-stage output. This can be ordinary post-init evolution; this inspector does not reconstruct later lineage.",
        False,
        facts,
        [
            f"Treat this as existing Forge state and audit the current Genome with: python forge.py audit {genome_path}",
            "Review later receipts/state before deciding to reuse, archive, or replace anything.",
        ],
    )


def render_human(report: dict[str, Any]) -> str:
    lines = [
        "FORGE INIT INSPECTION",
        f"STATE: {report['state']}",
        f"OUTPUT: {report['output']}",
        f"WHY: {report['why']}",
        "SAFE TO RUN INIT HERE: " + ("YES" if report["safe_to_initialize_here"] else "NO"),
        "NEXT:",
    ]
    lines.extend(f"- {action}" for action in report["next_actions"])
    lines.append("BOUNDARY: READ ONLY — no repair, delete, archive, initialization, canonical mutation, promotion, or CANON authority.")
    return "\n".join(lines)


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(
        description="Explain an existing Forge init output without changing it."
    )
    root.add_argument("output", help="Genome output path that forge.py init held or may use")
    root.add_argument("--json", action="store_true", help="emit the machine-readable inspection receipt")
    return root


def main() -> int:
    args = parser().parse_args()
    report = inspect_init_output(args.output)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(render_human(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
