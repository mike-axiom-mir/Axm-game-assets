#!/usr/bin/env python3
"""Bounded evidence-improving rehearsal for AXM native painted-metal materials.

Adapted from the repair discipline in axm-framestate rehearsal:
produce -> measure -> propose one bounded change -> measure again -> accept only
when the targeted evidence improves and protected evidence does not regress.

This module never mutates the source material directory or Game Asset Genome.
Every candidate is written into a fresh attempt directory and failed attempts
remain visible.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import asdict, fields, replace
from pathlib import Path
from typing import Any

from native_pbr import PaintedMetalSpec, write_painted_metal
from native_pbr_signal_review import review_native_pbr

SCHEMA = "axm.game-assets.native-pbr-rehearsal/v0.1"
POLICY_SCHEMA = "axm.game-assets.native-pbr-rehearsal-policy/v0.1"
SUPPORTED_PBR_SCHEMA = "axm.game-assets.native-pbr.v0.2"


class NativePbrRehearsalError(ValueError):
    pass


def _sha256(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def _strict_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise NativePbrRehearsalError(f"duplicate JSON key: {key}")
        out[key] = value
    return out


def _load_json(path: Path) -> tuple[dict[str, Any], bytes]:
    try:
        raw = path.read_bytes()
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_strict_pairs)
    except NativePbrRehearsalError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise NativePbrRehearsalError(f"cannot read {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise NativePbrRehearsalError(f"{path} must contain one JSON object")
    return value, raw


def _spec_to_json(spec: PaintedMetalSpec) -> dict[str, Any]:
    value = asdict(spec)
    value["paint_rgb"] = list(spec.paint_rgb)
    value["metal_rgb"] = list(spec.metal_rgb)
    return value


def _spec_from_manifest(manifest: dict[str, Any]) -> PaintedMetalSpec:
    if manifest.get("schema") != SUPPORTED_PBR_SCHEMA:
        raise NativePbrRehearsalError(
            f"material schema must be {SUPPORTED_PBR_SCHEMA}"
        )
    raw = manifest.get("spec")
    if not isinstance(raw, dict):
        raise NativePbrRehearsalError("material spec must be an object")
    required = {item.name for item in fields(PaintedMetalSpec)}
    missing = sorted(required - set(raw))
    unknown = sorted(set(raw) - required)
    if missing or unknown:
        raise NativePbrRehearsalError(
            f"material spec fields differ; missing={missing!r}; unknown={unknown!r}"
        )

    def rgb(name: str) -> tuple[int, int, int]:
        value = raw[name]
        if (
            not isinstance(value, list)
            or len(value) != 3
            or any(isinstance(channel, bool) or not isinstance(channel, int) for channel in value)
            or any(channel < 0 or channel > 255 for channel in value)
        ):
            raise NativePbrRehearsalError(f"{name} must be three integer channels in [0,255]")
        return tuple(value)  # type: ignore[return-value]

    def number(name: str) -> float:
        value = raw[name]
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise NativePbrRehearsalError(f"{name} must be numeric")
        value = float(value)
        if not (-1.0e9 < value < 1.0e9):
            raise NativePbrRehearsalError(f"{name} is outside the rehearsal numeric bound")
        return value

    scratches = raw["scratches"]
    if isinstance(scratches, bool) or not isinstance(scratches, int) or scratches < 0:
        raise NativePbrRehearsalError("scratches must be a non-negative integer")

    return PaintedMetalSpec(
        paint_rgb=rgb("paint_rgb"),
        metal_rgb=rgb("metal_rgb"),
        paint_roughness=number("paint_roughness"),
        metal_roughness=number("metal_roughness"),
        wear=number("wear"),
        scratches=scratches,
        grain_scale=number("grain_scale"),
        height_grain_amplitude=number("height_grain_amplitude"),
        height_broad_amplitude=number("height_broad_amplitude"),
        height_scratch_depth=number("height_scratch_depth"),
        height_pit_depth=number("height_pit_depth"),
        pit_wear_strength=number("pit_wear_strength"),
        base_grain_variation=number("base_grain_variation"),
        roughness_grain_variation=number("roughness_grain_variation"),
        normal_strength=number("normal_strength"),
    )


def _source_state(manifest_path: Path) -> tuple[dict[str, Any], PaintedMetalSpec, int, int, str]:
    manifest, raw = _load_json(manifest_path)
    spec = _spec_from_manifest(manifest)

    size = manifest.get("size")
    if (
        not isinstance(size, list)
        or len(size) != 2
        or any(isinstance(value, bool) or not isinstance(value, int) for value in size)
        or size[0] != size[1]
        or size[0] < 8
    ):
        raise NativePbrRehearsalError(
            "rehearsal currently requires one square native PBR material size >= 8"
        )
    seed = manifest.get("seed")
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise NativePbrRehearsalError("native PBR seed must be an integer")
    return manifest, spec, size[0], seed, _sha256(raw)


def normalize_policy(policy: dict[str, Any] | None = None) -> dict[str, Any]:
    raw = dict(policy or {})
    allowed = {
        "schema",
        "max_passes",
        "min_normal_strength",
        "max_normal_strength",
        "near_flat_bootstrap_strength",
        "weak_z_scale",
    }
    unknown = sorted(set(raw) - allowed)
    if unknown:
        raise NativePbrRehearsalError(f"unknown rehearsal policy fields: {unknown!r}")
    if raw.get("schema", POLICY_SCHEMA) != POLICY_SCHEMA:
        raise NativePbrRehearsalError(f"policy schema must be {POLICY_SCHEMA}")

    max_passes = raw.get("max_passes", 4)
    if isinstance(max_passes, bool) or not isinstance(max_passes, int) or not 1 <= max_passes <= 12:
        raise NativePbrRehearsalError("max_passes must be an integer in [1,12]")

    def bounded(name: str, default: float, lo: float, hi: float) -> float:
        value = raw.get(name, default)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise NativePbrRehearsalError(f"{name} must be numeric")
        value = float(value)
        if not lo <= value <= hi:
            raise NativePbrRehearsalError(f"{name} must be within [{lo},{hi}]")
        return value

    minimum = bounded("min_normal_strength", 0.1, 0.0, 32.0)
    maximum = bounded("max_normal_strength", 8.0, 0.1, 32.0)
    bootstrap = bounded("near_flat_bootstrap_strength", 1.0, 0.1, 32.0)
    weak_z_scale = bounded("weak_z_scale", 0.65, 0.05, 0.95)
    if minimum > maximum:
        raise NativePbrRehearsalError("min_normal_strength cannot exceed max_normal_strength")
    if bootstrap > maximum:
        raise NativePbrRehearsalError("near_flat_bootstrap_strength cannot exceed max_normal_strength")

    normalized = {
        "schema": POLICY_SCHEMA,
        "max_passes": max_passes,
        "min_normal_strength": minimum,
        "max_normal_strength": maximum,
        "near_flat_bootstrap_strength": bootstrap,
        "weak_z_scale": weak_z_scale,
        "automatic_repairs": [
            "normal near-flat signal when the source height field has measured variation",
            "weak tangent-normal positive-Z by reducing normal strength",
        ],
        "non_repairs": [
            "base-color diversity",
            "roughness variation",
            "aesthetic quality",
            "art-direction fit",
            "physical PBR correctness",
        ],
    }
    normalized["policy_digest"] = _sha256(_canonical(normalized))
    return normalized


def _entry(review: dict[str, Any], entry_id: str) -> dict[str, Any] | None:
    audit = review.get("audit")
    if not isinstance(audit, dict):
        return None
    rows = audit.get("entries")
    if not isinstance(rows, list):
        return None
    for row in rows:
        if isinstance(row, dict) and row.get("id") == entry_id:
            return row
    return None


def _warning_count(review: dict[str, Any]) -> int:
    audit = review.get("audit", {})
    rows = audit.get("entries", []) if isinstance(audit, dict) else []
    count = 0
    for row in rows:
        if isinstance(row, dict):
            warnings = row.get("warnings", [])
            if isinstance(warnings, list):
                count += len(warnings)
    family = audit.get("family_warnings", []) if isinstance(audit, dict) else []
    if isinstance(family, list):
        count += len(family)
    return count + len(review.get("manifest_hash_mismatches", []))


def _normal_warnings(review: dict[str, Any]) -> set[str]:
    row = _entry(review, "normal")
    if not row or not isinstance(row.get("warnings"), list):
        return set()
    return {str(value) for value in row["warnings"]}


def _height_has_variation(review: dict[str, Any]) -> bool:
    row = _entry(review, "height")
    if not row or row.get("status") == "HOLD":
        return False
    signal = row.get("signal")
    if not isinstance(signal, dict):
        return False
    std = signal.get("std")
    if not isinstance(std, dict):
        return False
    try:
        spread = max(float(std.get(key, 0.0)) for key in ("r", "g", "b"))
        edge = float(signal.get("edge_energy", 0.0))
    except (TypeError, ValueError):
        return False
    return spread >= 1.5 or edge >= 0.002


def _map_hashes(review: dict[str, Any]) -> dict[str, str]:
    hashes: dict[str, str] = {}
    audit = review.get("audit")
    if not isinstance(audit, dict):
        return hashes
    rows = audit.get("entries")
    if not isinstance(rows, list):
        return hashes
    for row in rows:
        if not isinstance(row, dict):
            continue
        entry_id = row.get("id")
        digest = row.get("sha256")
        if isinstance(entry_id, str) and isinstance(digest, str):
            hashes[entry_id] = digest
    return hashes


def propose_repairs(
    spec: PaintedMetalSpec,
    review: dict[str, Any],
    policy: dict[str, Any],
) -> list[dict[str, Any]]:
    if review.get("status") == "HOLD":
        return []
    warnings = _normal_warnings(review)
    proposals: list[dict[str, Any]] = []

    if (
        {"near-flat-signal", "normal-map-near-grayscale"} & warnings
        and _height_has_variation(review)
    ):
        current = float(spec.normal_strength)
        if current < policy["max_normal_strength"]:
            candidate = (
                policy["near_flat_bootstrap_strength"]
                if current < policy["near_flat_bootstrap_strength"]
                else min(policy["max_normal_strength"], current * 1.75)
            )
            if candidate > current:
                proposals.append(
                    {
                        "code": "NORMAL_SIGNAL_NEAR_FLAT",
                        "parameter": "normal_strength",
                        "before": current,
                        "after": candidate,
                        "target_warnings": sorted(
                            {"near-flat-signal", "normal-map-near-grayscale"} & warnings
                        ),
                        "reason": (
                            "the generator's height payload has measured variation while "
                            "the tangent-normal payload is near-flat"
                        ),
                    }
                )

    if "normal-positive-z-weak" in warnings:
        current = float(spec.normal_strength)
        candidate = max(policy["min_normal_strength"], current * policy["weak_z_scale"])
        if candidate < current:
            proposals.append(
                {
                    "code": "NORMAL_POSITIVE_Z_WEAK",
                    "parameter": "normal_strength",
                    "before": current,
                    "after": candidate,
                    "target_warnings": ["normal-positive-z-weak"],
                    "reason": "bounded tangent-normal Z diagnostic is weak",
                }
            )
    return proposals


def _comparison(
    before_review: dict[str, Any],
    after_review: dict[str, Any],
    proposal: dict[str, Any],
) -> dict[str, Any]:
    before_normal = _normal_warnings(before_review)
    after_normal = _normal_warnings(after_review)
    targets = set(proposal["target_warnings"])
    before_target = len(before_normal & targets)
    after_target = len(after_normal & targets)
    before_total = _warning_count(before_review)
    after_total = _warning_count(after_review)
    before_hashes = _map_hashes(before_review)
    after_hashes = _map_hashes(after_review)

    protected_ids = sorted((set(before_hashes) | set(after_hashes)) - {"normal"})
    changed_protected = [
        entry_id
        for entry_id in protected_ids
        if before_hashes.get(entry_id) != after_hashes.get(entry_id)
    ]
    normal_changed = (
        before_hashes.get("normal") is not None
        and after_hashes.get("normal") is not None
        and before_hashes["normal"] != after_hashes["normal"]
    )
    accepted = bool(
        after_review.get("status") != "HOLD"
        and after_target < before_target
        and after_total <= before_total
        and not changed_protected
        and normal_changed
    )
    return {
        "accepted": accepted,
        "target_warning_count_before": before_target,
        "target_warning_count_after": after_target,
        "total_warning_count_before": before_total,
        "total_warning_count_after": after_total,
        "protected_map_hashes_unchanged": not changed_protected,
        "changed_protected_maps": changed_protected,
        "normal_map_changed": normal_changed,
        "rule": (
            "targeted normal warnings must decrease; total warnings may not increase; "
            "candidate may not HOLD; every non-normal payload hash must remain exact; "
            "the normal payload must actually change"
        ),
    }


def rehearse_native_pbr(
    manifest_path: str | Path,
    output_root: str | Path,
    *,
    policy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    source_path = Path(manifest_path).resolve()
    source_manifest, source_spec, size, seed, source_manifest_sha256 = _source_state(source_path)
    normalized_policy = normalize_policy(policy)
    output = Path(output_root).resolve()
    try:
        output.mkdir(parents=True, exist_ok=False)
    except FileExistsError as exc:
        raise NativePbrRehearsalError(f"rehearsal output already exists: {output}") from exc

    try:
        current_review = review_native_pbr(source_path)
    except Exception as exc:
        raise NativePbrRehearsalError(f"initial native PBR review failed: {exc}") from exc
    initial_review = current_review
    current_spec = source_spec
    current_manifest_path = source_path
    attempts: list[dict[str, Any]] = []
    accepted_count = 0
    stop_reason = "MAX_PASSES_REACHED"

    for pass_index in range(1, normalized_policy["max_passes"] + 1):
        proposals = propose_repairs(current_spec, current_review, normalized_policy)
        if not proposals:
            stop_reason = "NO_JUSTIFIED_AUTO_DELTA"
            break

        accepted_this_pass = False
        for attempt_index, proposal in enumerate(proposals, 1):
            candidate_spec = replace(
                current_spec,
                **{proposal["parameter"]: proposal["after"]},
            )
            candidate_dir = output / f"pass-{pass_index:02d}-attempt-{attempt_index:02d}"
            try:
                write_painted_metal(
                    candidate_dir,
                    size=size,
                    seed=seed,
                    spec=candidate_spec,
                )
                candidate_manifest_path = candidate_dir / "material.json"
                candidate_review = review_native_pbr(candidate_manifest_path)
                comparison = _comparison(current_review, candidate_review, proposal)
            except Exception as exc:
                attempts.append(
                    {
                        "pass": pass_index,
                        "attempt": attempt_index,
                        "proposal": proposal,
                        "candidate_spec": _spec_to_json(candidate_spec),
                        "candidate_dir": candidate_dir.name,
                        "accepted": False,
                        "error": str(exc),
                    }
                )
                continue

            attempt = {
                "pass": pass_index,
                "attempt": attempt_index,
                "proposal": proposal,
                "candidate_spec": _spec_to_json(candidate_spec),
                "candidate_dir": candidate_dir.name,
                "candidate_review_digest": candidate_review.get("review_digest"),
                "comparison": comparison,
                "accepted": comparison["accepted"],
            }
            attempts.append(attempt)
            if comparison["accepted"]:
                current_spec = candidate_spec
                current_review = candidate_review
                current_manifest_path = candidate_manifest_path
                accepted_count += 1
                accepted_this_pass = True
                break

        if not accepted_this_pass:
            stop_reason = "NO_EVIDENCE_IMPROVING_DELTA"
            break

    receipt: dict[str, Any] = {
        "schema": SCHEMA,
        "source": {
            "manifest_path": source_path.name,
            "manifest_file_sha256": source_manifest_sha256,
            "schema": source_manifest.get("schema"),
            "kind": source_manifest.get("kind"),
            "seed": seed,
            "size": [size, size],
        },
        "policy": normalized_policy,
        "initial_spec": _spec_to_json(source_spec),
        "final_spec": _spec_to_json(current_spec),
        "initial_review_digest": initial_review.get("review_digest"),
        "final_review_digest": current_review.get("review_digest"),
        "final_review_status": current_review.get("status"),
        "final_manifest_path": (
            str(current_manifest_path.relative_to(output))
            if output in current_manifest_path.parents
            else f"source:{source_path.name}"
        ),
        "attempts": attempts,
        "accepted_delta_count": accepted_count,
        "rejected_attempt_count": sum(not bool(item.get("accepted")) for item in attempts),
        "stop_reason": stop_reason,
        "source_manifest_unchanged": _sha256(source_path.read_bytes()) == source_manifest_sha256,
        "authority": {
            "source_mutation": False,
            "genome_mutation": False,
            "visual_approval": False,
            "automatic_promotion": False,
            "release": False,
            "merge": False,
            "canon": False,
        },
        "truth_boundary": {
            "quality_claim": (
                "bounded technical normal-signal rehearsal only; accepted candidates "
                "improve named signal warnings without changing non-normal payloads"
            ),
            "aesthetic_quality_proven": False,
            "physical_pbr_correctness_proven": False,
            "art_direction_fit_proven": False,
            "engine_parity_proven": False,
        },
        "provenance": {
            "mechanism_source": (
                "mike-axiom-mir/axm-framestate rehearsal evidence-improvement discipline"
            ),
            "implementation": "AXM Game Asset Forge native Python adaptation",
        },
    }
    receipt["rehearsal_digest"] = _sha256(_canonical(receipt))
    receipt_path = output / "rehearsal-receipt.json"
    with receipt_path.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(receipt, handle, indent=2, sort_keys=True, ensure_ascii=False)
        handle.write("\n")
    return receipt


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Rehearse one native painted-metal material without mutating its source state"
        )
    )
    parser.add_argument("manifest", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--max-passes", type=int, default=4)
    args = parser.parse_args(argv)
    try:
        receipt = rehearse_native_pbr(
            args.manifest,
            args.output,
            policy={"max_passes": args.max_passes},
        )
    except NativePbrRehearsalError as exc:
        parser.error(str(exc))
    print(json.dumps(receipt, sort_keys=True, separators=(",", ":"), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
