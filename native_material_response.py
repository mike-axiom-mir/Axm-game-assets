#!/usr/bin/env python3
"""Bounded material-response intent for AXM Game Asset Forge.

This is a standalone Forge-native adapter over a pinned AXM-owned donor contract.
It preserves material behaviour intent such as subsurface, sheen, anisotropy,
clear-coat, transmission, iridescence and wear layering without claiming that a
specific renderer has implemented those lobes.

Donor snapshot:
mike-axiom-mir/axm-universal-creation@
5a6356270d0c7822576239b99c2b3ca3371cfdd7
"""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any

PACK_PATH = Path(__file__).with_name("seed_data") / "material_response_v01.json"
ORGANS_PATH = Path(__file__).with_name("seed_data") / "material_response_organs_v01.json"

SCHEMA = "axm.game-assets.material-response-resolution/v0.1"
EVIDENCE = "declared_contract_match_not_tested"
DONOR = {
    "repository": "mike-axiom-mir/axm-universal-creation",
    "commit": "5a6356270d0c7822576239b99c2b3ca3371cfdd7",
    "pack_path": "src/axm_uc/data/material_response/pack.json",
    "organs_path": "src/axm_uc/data/material_response/organs.json",
    "integration": (
        "Pinned AXM-owned donor data copied into Game Asset Forge; no runtime "
        "dependency on Universal Creation."
    ),
}

BASE_KEYS = {"base_color", "roughness", "metallic", "specular", "ior", "note"}
ORGAN_BY_KEY = {
    "subsurface": "surface.subsurface",
    "sheen": "surface.sheen",
    "anisotropy": "surface.anisotropy",
    "clearcoat": "surface.coat",
    "breakup": "surface.breakup",
    "transmission": "surface.transmission",
    "transmission_tint": "surface.transmission",
    "absorption": "surface.transmission",
    "dispersion": "surface.transmission",
    "iridescence": "surface.iridescence",
    "layers": "surface.wear_layer",
    "flake": "surface.coat",
}


class MaterialResponseError(ValueError):
    pass


def _load(path: Path) -> Any:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise MaterialResponseError(f"cannot load material-response data: {path}: {exc}") from exc
    return value


def _sha(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _organ_records() -> dict[str, dict[str, Any]]:
    raw = _load(ORGANS_PATH)
    if not isinstance(raw, list):
        raise MaterialResponseError("material-response organ source must be a list")
    out: dict[str, dict[str, Any]] = {}
    for row in raw:
        if not isinstance(row, dict) or row.get("format") != "axm-material-response-organ":
            raise MaterialResponseError("invalid material-response organ record")
        organ_id = row.get("id")
        if not isinstance(organ_id, str) or not organ_id or organ_id in out:
            raise MaterialResponseError("material-response organ ids must be unique non-empty strings")
        out[organ_id] = row
    return out


def _pack() -> dict[str, Any]:
    raw = _load(PACK_PATH)
    if not isinstance(raw, dict) or raw.get("format") != "axm-material-response-pack":
        raise MaterialResponseError("invalid material-response pack")
    families = raw.get("families")
    if not isinstance(families, list) or not families:
        raise MaterialResponseError("material-response pack has no families")
    return raw


def _active(value: Any, key: str, response: dict[str, Any]) -> bool:
    if key == "transmission":
        weight = value.get("weight", 0) if isinstance(value, dict) else value
        return isinstance(weight, (int, float)) and not isinstance(weight, bool) and abs(float(weight)) > 1e-12
    if key in {"transmission_tint", "absorption", "dispersion"}:
        return _active(response.get("transmission", 0), "transmission", response)
    if key == "layers":
        return isinstance(value, list) and any(
            isinstance(layer, dict)
            and isinstance(layer.get("weight", 1), (int, float))
            and not isinstance(layer.get("weight", 1), bool)
            and abs(float(layer.get("weight", 1))) > 1e-12
            for layer in value
        )
    if key == "anisotropy":
        return isinstance(value, dict) and isinstance(value.get("strength", 0), (int, float)) and abs(float(value.get("strength", 0))) > 1e-12
    if key == "breakup":
        if not isinstance(value, dict):
            return False
        return any(
            isinstance(v, (int, float))
            and not isinstance(v, bool)
            and abs(float(v)) > 1e-12
            for k, v in value.items()
            if k not in {"scale_mm", "octaves"}
        )
    if key in {"subsurface", "sheen", "clearcoat", "iridescence", "flake"}:
        return isinstance(value, dict) and isinstance(value.get("weight", 0), (int, float)) and float(value.get("weight", 0)) > 1e-12
    return value is not None


def active_organs(response: dict[str, Any]) -> list[str]:
    if not isinstance(response, dict):
        raise MaterialResponseError("material response must be an object")
    records = _organ_records()
    active: set[str] = set()
    for key, value in response.items():
        if key in BASE_KEYS:
            continue
        organ_id = ORGAN_BY_KEY.get(key)
        if organ_id is None:
            raise MaterialResponseError(f"unknown material-response key: {key}")
        if organ_id not in records:
            raise MaterialResponseError(f"missing organ contract: {organ_id}")
        if _active(value, key, response):
            active.add(organ_id)
    return sorted(active)


def _deep_merge(base: Any, patch: Any) -> Any:
    if isinstance(base, dict) and isinstance(patch, dict):
        out = copy.deepcopy(base)
        for key, value in patch.items():
            out[key] = _deep_merge(out[key], value) if key in out else copy.deepcopy(value)
        return out
    return copy.deepcopy(patch)


def resolve_material_response(
    family: str,
    *,
    variant: str | None = None,
    overrides: dict[str, Any] | None = None,
    base_color: list[float] | None = None,
) -> dict[str, Any]:
    if not isinstance(family, str) or not family.strip():
        raise MaterialResponseError("family must be non-empty text")
    family = family.strip()
    pack = _pack()
    matches = [row for row in pack["families"] if row.get("id") == family]
    if len(matches) != 1:
        raise MaterialResponseError(f"unknown material-response family: {family}")
    item = matches[0]
    response = copy.deepcopy(item.get("response"))
    if not isinstance(response, dict):
        raise MaterialResponseError(f"family {family} has no response object")
    if variant is not None:
        variants = item.get("variants", {})
        if not isinstance(variant, str) or not isinstance(variants, dict) or variant not in variants:
            raise MaterialResponseError(f"unknown {family} variant: {variant}")
        response = _deep_merge(response, variants[variant])
    if overrides is not None:
        if not isinstance(overrides, dict):
            raise MaterialResponseError("overrides must be an object")
        response = _deep_merge(response, overrides)
    if base_color is not None:
        if not isinstance(base_color, list) or len(base_color) != 3:
            raise MaterialResponseError("base_color must contain RGB values")
        response["base_color"] = [float(v) for v in base_color]

    organs = active_organs(response)
    return {
        "schema": SCHEMA,
        "family": family,
        "variant": variant,
        "purpose": item.get("purpose"),
        "response": response,
        "active_organs": organs,
        "evidence": EVIDENCE,
        "renderer_binding": (
            "HOLD_RENDERER_BINDING_NOT_TESTED" if organs else "PASS_NO_ACTIVE_ORGANS"
        ),
        "source": {
            "donor": copy.deepcopy(DONOR),
            "pack_sha256": _sha(PACK_PATH),
            "organs_sha256": _sha(ORGANS_PATH),
        },
        "truth": (
            "This resolves detailed material behaviour intent above texture/channel "
            "values. It does not prove that any Game Asset Forge renderer or target "
            "engine has bound the active response organs."
        ),
    }


def material_response_catalog() -> dict[str, Any]:
    pack = _pack()
    organs = _organ_records()
    return {
        "schema": "axm.game-assets.material-response-catalog/v0.1",
        "families": [
            {
                "id": row["id"],
                "purpose": row.get("purpose"),
                "variants": sorted(row.get("variants", {})),
            }
            for row in pack["families"]
        ],
        "organs": [
            {
                "id": row["id"],
                "name": row.get("name"),
                "evidence": row.get("evidence"),
                "verify": copy.deepcopy(row.get("verify", [])),
            }
            for row in sorted(organs.values(), key=lambda item: item["id"])
        ],
        "counts": {"families": len(pack["families"]), "organs": len(organs)},
        "renderer_binding": "NOT_CLAIMED",
        "evidence": EVIDENCE,
        "source": {
            "donor": copy.deepcopy(DONOR),
            "pack_sha256": _sha(PACK_PATH),
            "organs_sha256": _sha(ORGANS_PATH),
        },
    }
