#!/usr/bin/env python3
import json
from pathlib import Path

from native_asset_edit import apply_edit_packet, validate_packet, validate_surface

ROOT = Path("examples")


def load(name: str):
    return json.loads((ROOT / name).read_text(encoding="utf-8"))


def run() -> None:
    character_surface = load("sentinel-player-edit-surface.json")
    character_packet = load("sentinel-player-edit-packet.json")
    weapon_surface = load("sentinel-weapon-edit-surface.json")
    weapon_packet = load("sentinel-weapon-edit-packet.json")

    for surface in (character_surface, weapon_surface):
        report = validate_surface(surface)
        assert report["status"] == "pass", report

    for packet, surface in ((character_packet, character_surface), (weapon_packet, weapon_surface)):
        report = validate_packet(packet, surface)
        assert report["status"] == "pass", report

    character_result = apply_edit_packet({}, character_surface, character_packet)
    weapon_result = apply_edit_packet({}, weapon_surface, weapon_packet)

    assert character_result["asset_family"] == "character"
    assert character_result["variant_state"]["character"]["face"]["nose_width"] == 0.42
    assert character_result["variant_state"]["character"]["history"]["left_cheek_scar"] is True
    assert character_result["variant_state"]["character"]["gear"]["outer_torso"] == "scout"

    assert weapon_result["asset_family"] == "weapon"
    assert weapon_result["variant_state"]["weapon"]["barrel"]["length_class"] == "compact"
    assert weapon_result["variant_state"]["weapon"]["materials"]["wear_amount"] == 0.62
    assert weapon_result["variant_state"]["weapon"]["environment"]["winter_wrap"] is True

    assert character_result["truth"]["authority"] == "derived_variant_state_only"
    assert weapon_result["truth"]["authority"] == "derived_variant_state_only"
    assert character_result["variant_digest"] != weapon_result["variant_digest"]

    print("ASSET EDIT EXAMPLES PASS", {
        "character_variant": character_result["variant_digest"],
        "weapon_variant": weapon_result["variant_digest"]
    })


if __name__ == "__main__":
    run()
