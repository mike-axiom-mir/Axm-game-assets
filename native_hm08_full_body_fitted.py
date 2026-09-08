#!/usr/bin/env python3
"""Parallel fitted Sentinel full-body delivery for a clean armor-fit A/B.

The current equipped-body builder remains the control. This wrapper temporarily
substitutes only its armor builder with a derived conforming adapter, producing
the same character layers/materials while changing armor geometry fit only.
Canonical armor v0.2 is never overwritten.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import native_hm08_full_body_current as current
from native_armor_conform import conform_sentinel_armor
from native_armor_fit_evidence import armor_fit_evidence
from native_geometry import combine
from native_hm08_sentinel_armor import build_sentinel_rigid_armor as build_raw_armor

SCHEMA = "axm.game-assets.hm08-full-body-fitted.v0.1"
ASSET_NAME = "sentinel_hm08_full_body_fitted_v0_1"


def _sha(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def build_fitted_full_body_package(output: str | Path, *, texture_size: int = 128) -> dict[str, object]:
    root = Path(output)
    root.mkdir(parents=True, exist_ok=True)
    fit_receipt: dict[str, object] = {}

    def fitted_armor_builder(body_m):
        primary, primary_uv, accent, accent_uv, armor = build_raw_armor(body_m)
        baseline = armor_fit_evidence(body_m, combine([primary, accent], name="sentinel_raw_armor_fit_subject"))
        fitted_primary, fitted_accent, conform = conform_sentinel_armor(body_m, primary, accent)
        fitted = armor_fit_evidence(body_m, combine([fitted_primary, fitted_accent], name="sentinel_fitted_armor_fit_subject"))
        fit_receipt.update({
            "schema": "axm.game-assets.sentinel-static-armor-fit.v0.1",
            "baseline": baseline,
            "fitted": fitted,
            "conform": conform,
            "acceptance": {
                "obvious_float_repaired": fitted["fractions"]["obviously_floating"] < 0.02,
                "median_clearance_repaired": fitted["signed_normal_offset_m"]["median"] < 0.035,
                "no_penetration_regression": fitted["fractions"]["likely_interpenetrating"] < 0.05,
                "improves_intended_band": fitted["fractions"]["within_intended_clearance"] > baseline["fractions"]["within_intended_clearance"],
            },
            "truth": {
                "canonical_armor_mutated": False,
                "visual_promotion_required": True,
                "notes": [
                    "The raw segmented armor remains the canonical source layer; this receipt describes a derived fitted delivery only.",
                    "Nearest-body-normal clearance is an approximate static metric and must be followed by real Godot A/B evidence.",
                ],
            },
        })
        if not all(fit_receipt["acceptance"].values()):
            raise ValueError(f"fitted armor did not clear static fit gate: {fit_receipt['acceptance']}")
        fitted_armor = dict(armor)
        fitted_armor["delivery_fit"] = fit_receipt
        fitted_armor["truth"] = dict(armor["truth"])
        fitted_armor["truth"]["production_armor_claim"] = False
        fitted_armor["truth"]["notes"] = list(armor["truth"]["notes"]) + [
            "A reversible body-normal conform pass is applied only to this fitted delivery; raw segmented armor remains reconstructable."
        ]
        return fitted_primary, primary_uv, fitted_accent, accent_uv, fitted_armor

    original_builder = current.build_sentinel_rigid_armor
    original_asset_name = current.ASSET_NAME
    try:
        current.build_sentinel_rigid_armor = fitted_armor_builder
        current.ASSET_NAME = ASSET_NAME
        base = current.build_current_full_body_package(root, texture_size=texture_size)
    finally:
        current.build_sentinel_rigid_armor = original_builder
        current.ASSET_NAME = original_asset_name

    wrapper: dict[str, object] = {
        "schema": SCHEMA,
        "asset": ASSET_NAME,
        "candidate_role": "armor_fit_ab_candidate",
        "control_builder_schema": base["schema"],
        "control_candidate_role": base["candidate_role"],
        "changed_variable": "rigid_armor_static_fit_only",
        "armor_fit": fit_receipt,
        "delivery": base["delivery"],
        "base_acceptance": base["acceptance"],
        "acceptance": {
            "base_character_remains_green": all(base["acceptance"].values()),
            "fit_gate_green": all(fit_receipt["acceptance"].values()),
            "fourteen_materials_retained": base["delivery"]["material_count"] == 14,
            "fourteen_primitives_retained": base["delivery"]["primitive_count"] == 14,
        },
        "truth": {
            "automatic_visual_promotion": False,
            "high_end_character_claim": False,
            "notes": [
                "This A/B candidate changes armor fit only. Face, hair, undersuit, extremity gear, material recipes and camera evidence remain control-equivalent.",
                "Static fit metrics are necessary evidence but real Godot views decide whether the conforming transform preserves desirable hard-surface form.",
            ],
        },
    }
    payload = (json.dumps(wrapper, indent=2, sort_keys=True) + "\n").encode("utf-8")
    (root / "fitted-body-package.json").write_bytes(payload)
    wrapper["manifest_sha256"] = _sha(payload)
    if not all(wrapper["acceptance"].values()):
        raise ValueError(f"fitted full-body package failed: {wrapper['acceptance']}")
    return wrapper


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("output", nargs="?", default="build/hm08-full-body-fitted")
    parser.add_argument("--texture-size", type=int, default=128)
    args = parser.parse_args()
    result = build_fitted_full_body_package(args.output, texture_size=args.texture_size)
    print(json.dumps({"acceptance": result["acceptance"], "armor_fit": result["armor_fit"], "delivery": result["delivery"]}, indent=2))
