#!/usr/bin/env python3
"""Bounded intent-to-manufacturing planner for AXM Game Asset Forge.

The Forge already owns rich specialist machinery, but callers should not need to
know every internal module name. This router converts one explicit asset intent
into a family-grounded production plan. It reads the canonical family registry,
keeps ambiguity as HOLD, and never treats a plan as execution or acceptance.

This is intentionally narrower than a general language model. An AI or human can
supply stronger explicit fields; ordinary language is only used for bounded
family/requirement extraction.
"""
from __future__ import annotations

import copy
import hashlib
import json
import re
from pathlib import Path
from typing import Any

SCHEMA = "axm.game-assets.asset-intent/v0.1"
PLAN_SCHEMA = "axm.game-assets.asset-intent-plan/v0.1"
FAMILIES_PATH = Path(__file__).with_name("asset_genomes") / "families.json"

ALIASES = {
    "character": {"character", "person", "human", "humanoid", "npc", "creature", "avatar", "race"},
    "weapon": {"weapon", "gun", "rifle", "pistol", "sword", "staff", "bow"},
    "armor_clothing": {"armor", "armour", "clothing", "garment", "outfit", "helmet", "boot"},
    "prop": {"prop", "object", "furniture", "tool", "container"},
    "building": {"building", "house", "tower", "factory", "structure"},
    "environment_kit": {"environment", "biome", "level-kit", "world-kit", "environment-kit"},
    "vegetation": {"vegetation", "tree", "plant", "bush", "grass", "flower"},
    "material": {"material", "surface", "shader", "texture"},
    "vfx": {"vfx", "effect", "particle", "smoke", "fire", "magic-effect"},
}

COMMON_BLOCKS = [
    {"id": "intake", "purpose": "bind identity, units, provenance, quality and budgets"},
    {"id": "source-state", "purpose": "retain editable construction causes before deliveries"},
    {"id": "evidence", "purpose": "separate structural, visual, motion/runtime and provenance evidence"},
]

FAMILY_BLOCKS = {
    "character": [
        {"id": "character-source-profile", "module": "native_character_source_profile.py", "purpose": "race/body-family, semantic parts, sockets, clothing regions and material-response intent"},
        {"id": "form", "module": "native_form_recipe.py", "purpose": "source-first reusable body/accessory form construction when procedural geometry is appropriate"},
        {"id": "surface", "module": "native_surface_families.py", "purpose": "deterministic texture/material map families"},
        {"id": "material-response", "module": "native_material_response.py", "purpose": "subsurface/sheen/anisotropy/coat/transmission/iridescence/layering intent"},
        {"id": "rig-skin-motion", "module": "native_character_state.py", "purpose": "skeleton, skin, morph, animation and contact evidence"},
        {"id": "character-delivery", "module": "native_character_gltf.py", "purpose": "runtime character glTF delivery"},
    ],
    "weapon": [
        {"id": "form", "module": "native_form_recipe.py", "purpose": "reusable source-first form construction"},
        {"id": "construction", "module": "native_construction_kit.py", "purpose": "semantic hard-surface construction"},
        {"id": "surface", "module": "native_surface_families.py", "purpose": "PBR map families and wear signals"},
        {"id": "material-response", "module": "native_material_response.py", "purpose": "metal/paint/rubber/wood response intent"},
        {"id": "attachments", "module": "native_attachment.py", "purpose": "attachment/socket semantics and contact"},
        {"id": "delivery", "module": "native_gltf.py", "purpose": "runtime glTF delivery"},
    ],
    "armor_clothing": [
        {"id": "character-fit-semantics", "module": "native_character_source_profile.py", "purpose": "body-family regions and attachment semantics"},
        {"id": "cloth", "module": "native_cloth.py", "purpose": "cloth state/constraints where applicable"},
        {"id": "rigid-form", "module": "native_form_recipe.py", "purpose": "rigid and patterned components"},
        {"id": "surface", "module": "native_surface_families.py", "purpose": "fabric/metal/rubber maps"},
        {"id": "material-response", "module": "native_material_response.py", "purpose": "sheen/layering/coat and other surface response intent"},
    ],
    "prop": [
        {"id": "form", "module": "native_form_recipe.py", "purpose": "reusable source-first form construction"},
        {"id": "construction", "module": "native_construction_kit.py", "purpose": "semantic assemblies"},
        {"id": "surface", "module": "native_surface_families.py", "purpose": "material maps"},
        {"id": "material-response", "module": "native_material_response.py", "purpose": "detailed response intent"},
        {"id": "collision", "module": "native_geometry.py", "purpose": "bounded collision evidence"},
    ],
    "building": [
        {"id": "form", "module": "native_form_recipe.py", "purpose": "profile/path/loft based components"},
        {"id": "construction", "module": "native_construction_kit.py", "purpose": "beams, pipes, rails and semantic construction detail"},
        {"id": "surface", "module": "native_surface_families.py", "purpose": "building material maps"},
        {"id": "material-response", "module": "native_material_response.py", "purpose": "layered/weathered material behavior intent"},
        {"id": "collision-navigation", "module": "native_geometry.py", "purpose": "structural geometry/collision evidence; navigation remains separately bounded"},
    ],
    "environment_kit": [
        {"id": "form", "module": "native_form_recipe.py", "purpose": "modular source-first forms"},
        {"id": "construction", "module": "native_construction_kit.py", "purpose": "semantic world detail components"},
        {"id": "surface", "module": "native_surface_families.py", "purpose": "environment material maps"},
        {"id": "material-response", "module": "native_material_response.py", "purpose": "weathered/layered response intent"},
        {"id": "lod", "module": "native_geometry.py", "purpose": "LOD/collision substrate with family-specific preservation gates"},
    ],
    "vegetation": [
        {"id": "form", "module": "native_form_recipe.py", "purpose": "trunk/branch/profile/path source construction"},
        {"id": "surface", "module": "native_surface_families.py", "purpose": "wood/leaf material maps"},
        {"id": "material-response", "module": "native_material_response.py", "purpose": "wood subsurface/anisotropy and leaf transmission response intent"},
        {"id": "motion-lod", "module": "native_geometry.py", "purpose": "geometry/LOD substrate; wind behavior requires separate evidence"},
    ],
    "material": [
        {"id": "surface", "module": "native_surface_families.py", "purpose": "deterministic authored map generation"},
        {"id": "material-response", "module": "native_material_response.py", "purpose": "detailed response family/organs above maps"},
        {"id": "material-audit", "module": "native_material_signal_audit.py", "purpose": "signal/evidence inspection"},
    ],
    "vfx": [
        {"id": "vfx-state", "module": "native_vfx.py", "purpose": "emitter/effect state"},
        {"id": "material-response", "module": "native_material_response.py", "purpose": "surface response when VFX includes rendered material surfaces"},
        {"id": "engine-evidence", "purpose": "target-engine timing/exposure/performance evidence"},
    ],
}


class AssetIntentError(ValueError):
    pass


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def _digest(value: Any) -> str:
    return "sha256:" + hashlib.sha256(_canonical(value)).hexdigest()


def _families() -> dict[str, dict[str, Any]]:
    raw = json.loads(FAMILIES_PATH.read_text(encoding="utf-8"))
    rows = raw.get("families") if isinstance(raw, dict) else None
    if not isinstance(rows, list):
        raise AssetIntentError("asset family registry is invalid")
    return {row["id"]: row for row in rows if isinstance(row, dict) and isinstance(row.get("id"), str)}


def _words(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+(?:-[a-z0-9]+)?", text.casefold()))


def compile_asset_intent(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise AssetIntentError("asset intent must be an object")
    allowed = {
        "schema", "prompt", "asset_id", "family", "quality_tier",
        "deliverables", "requirements", "constraints", "source",
    }
    unexpected = sorted(set(raw) - allowed)
    if unexpected:
        raise AssetIntentError(f"asset intent contains unsupported fields: {unexpected}")
    if raw.get("schema", SCHEMA) != SCHEMA:
        raise AssetIntentError(f"asset intent must use schema {SCHEMA}")
    prompt = raw.get("prompt", "")
    if not isinstance(prompt, str):
        raise AssetIntentError("prompt must be text")
    explicit_family = raw.get("family")
    if explicit_family is not None and not isinstance(explicit_family, str):
        raise AssetIntentError("family must be text when supplied")
    quality = raw.get("quality_tier", "gameplay")
    if not isinstance(quality, str) or not quality.strip():
        raise AssetIntentError("quality_tier must be non-empty text")
    lists = {}
    for field in ("deliverables", "requirements", "constraints"):
        value = raw.get(field, [])
        if isinstance(value, str):
            value = [value]
        if not isinstance(value, list) or any(not isinstance(item, str) or not item.strip() for item in value):
            raise AssetIntentError(f"{field} must be text or a text list")
        lists[field] = list(dict.fromkeys(item.strip() for item in value))

    contract = {
        "schema": SCHEMA,
        "prompt": prompt.strip(),
        "asset_id": raw.get("asset_id"),
        "explicit_family": explicit_family.strip() if isinstance(explicit_family, str) else None,
        "quality_tier": quality.strip(),
        **lists,
        "source": copy.deepcopy(raw.get("source", {})),
    }
    contract["intent_digest"] = _digest(contract)
    return contract


def route_asset_intent(raw: Any) -> dict[str, Any]:
    contract = compile_asset_intent(raw)
    families = _families()
    explicit = contract["explicit_family"]
    candidates: list[dict[str, Any]] = []

    if explicit is not None:
        if explicit not in families:
            return {
                "schema": PLAN_SCHEMA,
                "status": "HOLD_UNKNOWN_FAMILY",
                "intent": contract,
                "known_families": sorted(families),
                "automatic_execution": False,
                "automatic_genome_mutation": False,
                "automatic_canon": False,
            }
        selected = explicit
        selection_basis = "caller-explicit-family"
    else:
        words = _words(contract["prompt"])
        for family_id in sorted(families):
            aliases = ALIASES.get(family_id, {family_id.replace("_", "-")})
            overlap = sorted(words & aliases)
            if overlap:
                candidates.append({"family": family_id, "matched_tokens": overlap})
        if len(candidates) != 1:
            return {
                "schema": PLAN_SCHEMA,
                "status": "HOLD_AMBIGUOUS_FAMILY" if candidates else "HOLD_FAMILY_NOT_INFERRED",
                "intent": contract,
                "candidates": candidates,
                "known_families": sorted(families),
                "automatic_execution": False,
                "automatic_genome_mutation": False,
                "automatic_canon": False,
                "truth": "Bounded word overlap is routing evidence, not general semantic understanding.",
            }
        selected = candidates[0]["family"]
        selection_basis = "unique-bounded-language-family-match"

    family = families[selected]
    blocks = copy.deepcopy(COMMON_BLOCKS + FAMILY_BLOCKS.get(selected, []))
    requirements_text = " ".join(contract["requirements"] + [contract["prompt"]]).casefold()
    if any(token in requirements_text for token in ("animated", "animation", "motion", "rigged", "rig")):
        if selected != "character":
            blocks.append({
                "id": "motion-requirement",
                "purpose": "family-specific motion/rigging evidence required; no generic character rig assumption",
                "status": "REQUIRES_FAMILY_SPECIFIC_BINDING",
            })
    if any(token in requirements_text for token in ("engine", "godot", "unreal", "three.js", "runtime")):
        blocks.append({
            "id": "runtime-validation",
            "purpose": "real target-engine import/render/performance evidence",
        })

    plan = {
        "schema": PLAN_SCHEMA,
        "status": "PLANNED_NOT_EXECUTED",
        "intent": contract,
        "selected_family": selected,
        "selection_basis": selection_basis,
        "family_editable_domains": copy.deepcopy(family.get("editable_domains", [])),
        "production_blocks": blocks,
        "source_authority": "Game Asset Genome + canonical source state",
        "deliveries_are_secondary": True,
        "automatic_execution": False,
        "automatic_genome_mutation": False,
        "automatic_vault_admission": False,
        "automatic_visual_acceptance": False,
        "automatic_canon": False,
        "truth": (
            "This is a deterministic manufacturing plan over current Forge surfaces. "
            "It does not claim that every block is complete for every asset, that a "
            "planned path executed, or that quality/engine acceptance was earned."
        ),
    }
    plan["plan_digest"] = _digest(plan)
    return plan


def asset_intent_summary() -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "plan_schema": PLAN_SCHEMA,
        "families": sorted(_families()),
        "explicit_family_supported": True,
        "bounded_language_family_inference": True,
        "ambiguous_language_holds": True,
        "automatic_execution": False,
        "automatic_canon": False,
    }
