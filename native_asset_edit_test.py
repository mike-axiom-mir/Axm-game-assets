#!/usr/bin/env python3
from copy import deepcopy

from native_asset_edit import apply_edit_packet, digest, validate_packet, validate_surface


def surface():
    return {
        "schema": "axm.asset-edit-surface.v0.1",
        "surface_id": "sentinel-rpg-character-creator-v0.1",
        "asset_family": "character",
        "parameters": [
            {
                "id": "face.nose_width",
                "path": "character.face.nose_width",
                "type": "number",
                "minimum": -1.0,
                "maximum": 1.0,
                "default": 0.0,
                "editable_by": ["player", "ai"]
            },
            {
                "id": "face.cheekbone_strength",
                "path": "character.face.cheekbone_strength",
                "type": "number",
                "minimum": -1.0,
                "maximum": 1.0,
                "default": 0.0,
                "editable_by": ["player", "ai"]
            },
            {
                "id": "hair.style",
                "path": "character.hair.style",
                "type": "enum",
                "values": ["short_laid", "buzz", "bald"],
                "default": "short_laid",
                "editable_by": ["player", "ai"]
            },
            {
                "id": "debug.internal_lod_bias",
                "path": "runtime.debug_lod_bias",
                "type": "integer",
                "minimum": 0,
                "maximum": 3,
                "default": 0,
                "editable_by": ["tool"]
            }
        ]
    }


def packet():
    return {
        "schema": "axm.asset-edit-packet.v0.1",
        "surface_id": "sentinel-rpg-character-creator-v0.1",
        "base_genome_digest": "sha256:" + "a" * 64,
        "actor": {"kind": "player", "id": "local-player"},
        "operations": [
            {"op": "set", "parameter": "face.nose_width", "value": 0.42},
            {"op": "set", "parameter": "face.cheekbone_strength", "value": 0.28},
            {"op": "set", "parameter": "hair.style", "value": "short_laid"}
        ]
    }


def run() -> None:
    edit_surface = surface()
    edit_packet = packet()
    surface_report = validate_surface(edit_surface)
    assert surface_report["status"] == "pass", surface_report
    packet_report = validate_packet(edit_packet, edit_surface)
    assert packet_report["status"] == "pass", packet_report

    base = {"character": {"face": {"nose_width": 0.0}, "hair": {"style": "bald"}}}
    original = deepcopy(base)
    first = apply_edit_packet(base, edit_surface, edit_packet)
    second = apply_edit_packet(base, edit_surface, edit_packet)
    assert base == original, "applying an edit packet must not mutate canonical/base state"
    assert first == second, "same base/surface/packet must be deterministic"
    assert first["variant_state"]["character"]["face"]["nose_width"] == 0.42
    assert first["variant_state"]["character"]["face"]["cheekbone_strength"] == 0.28
    assert first["variant_state"]["character"]["hair"]["style"] == "short_laid"
    assert first["truth"]["canonical_state_mutated"] is False
    assert first["variant_digest"].startswith("sha256:")

    out_of_bounds = packet()
    out_of_bounds["operations"][0]["value"] = 2.0
    assert validate_packet(out_of_bounds, edit_surface)["status"] == "fail"

    undeclared = packet()
    undeclared["operations"].append({"op": "set", "parameter": "face.secret_vendor_slider", "value": 0.5})
    assert validate_packet(undeclared, edit_surface)["status"] == "fail"

    player_touches_tool = packet()
    player_touches_tool["operations"] = [{"op": "set", "parameter": "debug.internal_lod_bias", "value": 2}]
    assert validate_packet(player_touches_tool, edit_surface)["status"] == "fail"

    duplicate = packet()
    duplicate["operations"].append({"op": "set", "parameter": "face.nose_width", "value": -0.2})
    assert validate_packet(duplicate, edit_surface)["status"] == "fail"

    changed = packet()
    changed["operations"][0]["value"] = 0.43
    changed_result = apply_edit_packet(base, edit_surface, changed)
    assert changed_result["variant_digest"] != first["variant_digest"]
    assert digest(first["variant_state"]) != digest(changed_result["variant_state"])

    print("ASSET EDIT TEST PASS", {
        "surface": surface_report["surface_digest"],
        "variant": first["variant_digest"],
        "parameters": surface_report["parameters"]
    })


if __name__ == "__main__":
    run()
