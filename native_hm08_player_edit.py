#!/usr/bin/env python3
"""Bridge bounded RPG character edits into real hm08 facial target state.

This is deliberately a narrow first bridge. The player-facing edit surface
expresses semantic values around the current Sentinel baseline. Those values are
translated into existing sparse hm08 target weights, mixed onto the repaired
v0.2 human head, and emitted as a derived variant. The canonical seed remains
untouched.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from native_asset_edit import apply_edit_packet, digest, validate_packet, validate_surface
from native_hm08_face_proof import DEFAULT_WEIGHTS, SEED_ROOT
from native_targets import load_target, mix_targets
from native_uv import read_obj_uv, validate_uv, write_obj_uv

SCHEMA = "axm.game-assets.hm08-player-edit-bridge.v0.1"
SURFACE_PATH = Path("examples/sentinel-player-edit-surface.json")


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _mesh_digest(mesh) -> str:
    payload = {
        "vertices": [[round(v, 12) for v in row] for row in mesh.vertices],
        "faces": [list(face) for face in mesh.faces],
    }
    return digest(payload)


def semantic_face_to_target_weights(variant_state: dict[str, Any]) -> dict[str, float]:
    face = variant_state.get("character", {}).get("face", {})
    nose_bias = float(face.get("nose_width", 0.0))
    cheek_bias = float(face.get("cheekbone_strength", 0.0))

    # Current v0.1 target library contains increment targets only. Semantic 0
    # means the current Sentinel baseline. Negative values reduce that target
    # contribution toward the neutral hm08 seed; positive values strengthen it.
    nose_base = float(DEFAULT_WEIGHTS["nose-width1-incr"])
    cheek_base = float(DEFAULT_WEIGHTS["l-cheek-bones-incr"])
    return {
        "nose-width1-incr": _clamp(nose_base * (1.0 + nose_bias), 0.0, nose_base * 2.0),
        "l-cheek-bones-incr": _clamp(cheek_base * (1.0 + cheek_bias), 0.0, cheek_base * 2.0),
        "r-cheek-bones-incr": _clamp(cheek_base * (1.0 + cheek_bias), 0.0, cheek_base * 2.0),
    }


def build_player_face_variant(
    packet: dict[str, Any],
    *,
    surface: dict[str, Any] | None = None,
) -> tuple[Any, Any, dict[str, Any]]:
    surface = surface or json.loads(SURFACE_PATH.read_text(encoding="utf-8"))
    surface_report = validate_surface(surface)
    packet_report = validate_packet(packet, surface)
    if surface_report["status"] != "pass" or packet_report["status"] != "pass":
        raise ValueError(f"invalid player edit input: surface={surface_report} packet={packet_report}")

    base_variant_state = {
        "character": {
            "face": {
                "nose_width": 0.0,
                "cheekbone_strength": 0.0,
                "age_bias": 0.0,
            },
            "body": {"height_scale": 1.0},
            "hair": {"style": "short_laid", "color_family": "dark_brown"},
            "history": {"left_cheek_scar": False},
            "gear": {"outer_torso": "sentinel_standard"},
        }
    }
    edit_result = apply_edit_packet(base_variant_state, surface, packet)
    target_weights = semantic_face_to_target_weights(edit_result["variant_state"])

    seed_mesh, uvmap = read_obj_uv(SEED_ROOT / "head.obj", name="hm08_head_v0_2")
    uv_report = validate_uv(seed_mesh, uvmap)
    if uv_report["status"] != "pass":
        raise ValueError(f"preferred hm08 seed UV invalid: {uv_report}")
    library = {
        name: load_target(SEED_ROOT / "targets" / f"{name}.target", license="CC0-source-remap")
        for name in sorted(target_weights)
    }
    variant, mix_state = mix_targets(
        seed_mesh,
        library,
        target_weights,
        name="sentinel_player_face_variant",
    )
    if len(variant.vertices) != len(seed_mesh.vertices) or variant.faces != seed_mesh.faces:
        raise ValueError("player edit changed canonical hm08 topology")

    receipt = {
        "schema": SCHEMA,
        "surface_id": surface["surface_id"],
        "asset_family": "character",
        "base_genome_digest": packet["base_genome_digest"],
        "edit_variant_digest": edit_result["variant_digest"],
        "semantic_variant_state": edit_result["variant_state"],
        "target_weights": target_weights,
        "target_mix": mix_state,
        "mesh_digest": _mesh_digest(variant),
        "uv_method": uvmap.method,
        "truth": {
            "canonical_seed_mutated": False,
            "topology_changed": False,
            "bridge_scope": "nose_width_and_cheekbone_strength_only",
            "notes": [
                "Other player-facing parameters remain valid derived state but do not yet alter hm08 geometry in this bridge.",
                "v0.1 uses increment-only sparse targets, so negative semantic values reduce toward neutral hm08 rather than beyond it."
            ],
        },
    }
    receipt["receipt_digest"] = digest(receipt)
    return variant, uvmap, receipt


def write_player_face_variant(packet_path: str | Path, output: str | Path) -> dict[str, Any]:
    packet = json.loads(Path(packet_path).read_text(encoding="utf-8"))
    variant, uvmap, receipt = build_player_face_variant(packet)
    root = Path(output)
    root.mkdir(parents=True, exist_ok=True)
    write_obj_uv(variant, uvmap, root / "player-face.obj")
    payload = (json.dumps(receipt, indent=2, sort_keys=True) + "\n").encode("utf-8")
    (root / "player-face-edit-receipt.json").write_bytes(payload)
    receipt["receipt_file_sha256"] = "sha256:" + hashlib.sha256(payload).hexdigest()
    return receipt


if __name__ == "__main__":
    result = write_player_face_variant(
        "examples/sentinel-player-edit-packet.json",
        "build/sentinel-player-face",
    )
    print(json.dumps(result, indent=2, sort_keys=True))
