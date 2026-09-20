#!/usr/bin/env python3
"""Semantic source profile for whole characters in AXM Game Asset Forge.

Rig/skin/morph/animation state already has a separate native character-state
contract. This source profile captures the character identity and reusable
construction semantics that should survive before and after runtime compilation:
race/body family, semantic parts, attachment sockets, clothing regions and
material-response intent.
"""
from __future__ import annotations

import copy
import hashlib
import json
from typing import Any

from native_material_response import MaterialResponseError, resolve_material_response

SCHEMA = "axm.game-assets.character-source-profile/v0.1"
MAX_PARTS = 256
MAX_SOCKETS = 128
MAX_CLOTHING_REGIONS = 128


class CharacterSourceProfileError(ValueError):
    pass


def _canonical(value: Any) -> bytes:
    try:
        return json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise CharacterSourceProfileError("character source profile must be finite JSON") from exc


def _text(value: Any, label: str, maximum: int = 160) -> str:
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > maximum:
        raise CharacterSourceProfileError(
            f"{label} must be non-empty text up to {maximum} characters"
        )
    return value.strip()


def _vec3(value: Any, label: str) -> list[float]:
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        raise CharacterSourceProfileError(f"{label} must contain three numbers")
    result = []
    for item in value:
        if isinstance(item, bool) or not isinstance(item, (int, float)):
            raise CharacterSourceProfileError(f"{label} must contain numbers")
        result.append(float(item))
    return result


def compile_character_source_profile(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict) or raw.get("schema") != SCHEMA:
        raise CharacterSourceProfileError(f"profile must use schema {SCHEMA}")
    allowed = {
        "schema", "asset_id", "race_id", "body_family", "description",
        "parts", "sockets", "clothing_regions", "material_responses",
        "provenance", "metadata",
    }
    unexpected = sorted(set(raw) - allowed)
    if unexpected:
        raise CharacterSourceProfileError(
            f"profile contains unsupported fields: {unexpected}"
        )

    asset_id = _text(raw.get("asset_id"), "asset_id", 120)
    race_id = _text(raw.get("race_id"), "race_id", 120)
    body_family = _text(raw.get("body_family"), "body_family", 120)

    parts_raw = raw.get("parts", [])
    if not isinstance(parts_raw, list) or not 1 <= len(parts_raw) <= MAX_PARTS:
        raise CharacterSourceProfileError(
            f"parts must contain 1..{MAX_PARTS} semantic parts"
        )
    parts = []
    part_ids: set[str] = set()
    for index, row in enumerate(parts_raw):
        if not isinstance(row, dict) or set(row) - {"id", "role", "source_ref"}:
            raise CharacterSourceProfileError(f"parts[{index}] fields are invalid")
        part_id = _text(row.get("id"), f"parts[{index}].id", 80)
        if part_id in part_ids:
            raise CharacterSourceProfileError(f"duplicate part id {part_id!r}")
        part_ids.add(part_id)
        parts.append({
            "id": part_id,
            "role": _text(row.get("role", part_id), f"parts[{index}].role", 160),
            **({"source_ref": _text(row["source_ref"], f"parts[{index}].source_ref", 240)}
               if "source_ref" in row else {}),
        })

    sockets_raw = raw.get("sockets", [])
    if not isinstance(sockets_raw, list) or len(sockets_raw) > MAX_SOCKETS:
        raise CharacterSourceProfileError(
            f"sockets must contain at most {MAX_SOCKETS} entries"
        )
    sockets = []
    socket_ids: set[str] = set()
    for index, row in enumerate(sockets_raw):
        if not isinstance(row, dict) or set(row) - {"id", "part", "position", "purpose", "tags"}:
            raise CharacterSourceProfileError(f"sockets[{index}] fields are invalid")
        socket_id = _text(row.get("id"), f"sockets[{index}].id", 80)
        if socket_id in socket_ids:
            raise CharacterSourceProfileError(f"duplicate socket id {socket_id!r}")
        socket_ids.add(socket_id)
        part = _text(row.get("part"), f"sockets[{index}].part", 80)
        if part not in part_ids:
            raise CharacterSourceProfileError(
                f"socket {socket_id!r} references unknown part {part!r}"
            )
        tags = row.get("tags", [])
        if not isinstance(tags, list) or any(
            not isinstance(tag, str) or not tag.strip() for tag in tags
        ):
            raise CharacterSourceProfileError(f"sockets[{index}].tags must be text")
        sockets.append({
            "id": socket_id,
            "part": part,
            "position": _vec3(row.get("position"), f"sockets[{index}].position"),
            "purpose": _text(row.get("purpose", socket_id), f"sockets[{index}].purpose", 240),
            "tags": list(dict.fromkeys(tag.strip() for tag in tags)),
        })

    clothing_raw = raw.get("clothing_regions", [])
    if not isinstance(clothing_raw, list) or len(clothing_raw) > MAX_CLOTHING_REGIONS:
        raise CharacterSourceProfileError(
            f"clothing_regions must contain at most {MAX_CLOTHING_REGIONS} entries"
        )
    clothing_regions = []
    region_ids: set[str] = set()
    for index, row in enumerate(clothing_raw):
        if not isinstance(row, dict) or set(row) - {
            "id", "parts", "body_family", "attachment_tags", "fit_truth"
        }:
            raise CharacterSourceProfileError(
                f"clothing_regions[{index}] fields are invalid"
            )
        region_id = _text(row.get("id"), f"clothing_regions[{index}].id", 80)
        if region_id in region_ids:
            raise CharacterSourceProfileError(f"duplicate clothing region id {region_id!r}")
        region_ids.add(region_id)
        region_parts = row.get("parts")
        if (
            not isinstance(region_parts, list)
            or not region_parts
            or any(not isinstance(part, str) or not part.strip() for part in region_parts)
        ):
            raise CharacterSourceProfileError(
                f"clothing_regions[{index}].parts must be a non-empty text list"
            )
        region_parts = [part.strip() for part in region_parts]
        unknown = sorted(set(region_parts) - part_ids)
        if unknown:
            raise CharacterSourceProfileError(
                f"clothing region {region_id!r} references unknown parts {unknown}"
            )
        tags = row.get("attachment_tags", [])
        if not isinstance(tags, list) or any(
            not isinstance(tag, str) or not tag.strip() for tag in tags
        ):
            raise CharacterSourceProfileError(
                f"clothing_regions[{index}].attachment_tags must be text"
            )
        clothing_regions.append({
            "id": region_id,
            "parts": region_parts,
            "body_family": _text(
                row.get("body_family", body_family),
                f"clothing_regions[{index}].body_family",
                120,
            ),
            "attachment_tags": list(dict.fromkeys(tag.strip() for tag in tags)),
            "fit_truth": str(row.get(
                "fit_truth",
                "DECLARED_REGION_ONLY_NOT_GEOMETRIC_FIT_PROOF",
            )),
        })

    responses_raw = raw.get("material_responses", {})
    if not isinstance(responses_raw, dict):
        raise CharacterSourceProfileError("material_responses must be an object")
    material_responses: dict[str, Any] = {}
    material_holds: list[str] = []
    for target, spec in sorted(responses_raw.items()):
        if target != "default" and target not in part_ids:
            raise CharacterSourceProfileError(
                f"material response target {target!r} is not default or a known part"
            )
        if not isinstance(spec, dict) or "family" not in spec or set(spec) - {
            "family", "variant", "overrides", "base_color"
        }:
            raise CharacterSourceProfileError(
                f"material_responses.{target} requires family and optional variant/overrides/base_color"
            )
        try:
            resolved = resolve_material_response(
                spec["family"],
                variant=spec.get("variant"),
                overrides=copy.deepcopy(spec.get("overrides")),
                base_color=copy.deepcopy(spec.get("base_color")),
            )
        except MaterialResponseError as exc:
            raise CharacterSourceProfileError(
                f"material_responses.{target}: {exc}"
            ) from exc
        material_responses[target] = resolved
        if resolved["renderer_binding"] == "HOLD_RENDERER_BINDING_NOT_TESTED":
            material_holds.append(target)

    normalized = {
        "schema": SCHEMA,
        "asset_id": asset_id,
        "race_id": race_id,
        "body_family": body_family,
        "description": str(raw.get("description", "")),
        "parts": parts,
        "sockets": sockets,
        "clothing_regions": clothing_regions,
        "material_responses": material_responses,
        "material_response_holds": material_holds,
        "provenance": copy.deepcopy(raw.get("provenance", {})),
        "metadata": copy.deepcopy(raw.get("metadata", {})),
        "source_authority": True,
        "realization_is_secondary": True,
        "truth_boundary": {
            "race_and_body_family_are_source_semantics": True,
            "sockets_are_declared_attachment_semantics": True,
            "clothing_regions_are_declared_compatibility_regions": True,
            "clothing_fit_proven": False,
            "material_response_renderer_binding_proven": not material_holds,
            "rigging_or_animation_proven_by_this_profile": False,
            "automatic_genome_mutation": False,
            "automatic_vault_admission": False,
            "automatic_canon": False,
        },
    }
    normalized["profile_digest"] = "sha256:" + hashlib.sha256(
        _canonical(normalized)
    ).hexdigest()
    return normalized
