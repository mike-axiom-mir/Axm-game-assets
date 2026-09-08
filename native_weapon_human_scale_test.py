#!/usr/bin/env python3

from native_weapon_human_scale import DESIGN_SCALE, human_scale_weapon_evidence, sentinel_rifle_human_scale


def run() -> None:
    first = sentinel_rifle_human_scale()
    second = sentinel_rifle_human_scale()
    assert first.mesh.vertices == second.mesh.vertices
    assert first.mesh.faces == second.mesh.faces
    assert first.sockets == second.sockets
    assert first.components.keys() == second.components.keys()

    evidence = human_scale_weapon_evidence(first)
    assert evidence["schema"] == "axm.game-assets.sentinel-rifle-human-scale.v0.5"
    assert evidence["validation"]["status"] == "pass", evidence
    assert evidence["design_scale"] == list(DESIGN_SCALE)
    assert 0.92 <= evidence["overall_length_m"] <= 1.04, evidence
    assert 0.27 <= evidence["grip_socket_separation_m"] <= 0.30, evidence
    assert evidence["triangles"] > 2000
    assert evidence["component_count"] >= 60
    assert evidence["socket_count"] >= 6
    assert first.sockets["muzzle"].position[0] > first.sockets["support_grip"].position[0]
    assert first.sockets["support_grip"].position[0] > first.sockets["primary_grip"].position[0]
    assert evidence["truth"]["runtime_scale_required"] is False
    assert evidence["truth"]["runtime_scale"] == [1.0,1.0,1.0]
    assert evidence["truth"]["legacy_rifle_deleted"] is False
    assert evidence["truth"]["production_weapon_art_claim"] is False
    print("HUMAN-SCALE SENTINEL RIFLE TEST PASS", {
        "length_m": evidence["overall_length_m"],
        "grip_span_m": evidence["grip_socket_separation_m"],
        "triangles": evidence["triangles"],
        "components": evidence["component_count"],
    })


if __name__ == "__main__":
    run()
