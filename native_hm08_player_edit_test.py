#!/usr/bin/env python3
import json
from copy import deepcopy
from pathlib import Path

from native_hm08_player_edit import build_player_face_variant, semantic_face_to_target_weights


def load_packet():
    return json.loads(Path("examples/sentinel-player-edit-packet.json").read_text(encoding="utf-8"))


def run() -> None:
    packet = load_packet()
    first_mesh, first_uv, first = build_player_face_variant(packet)
    second_mesh, second_uv, second = build_player_face_variant(packet)

    assert first == second, "same player edit must produce identical receipt"
    assert first_mesh.vertices == second_mesh.vertices
    assert first_mesh.faces == second_mesh.faces
    assert first_uv.uvs == second_uv.uvs
    assert first["truth"]["canonical_seed_mutated"] is False
    assert first["truth"]["topology_changed"] is False
    assert first["target_weights"]["nose-width1-incr"] > 0.35
    assert first["target_weights"]["l-cheek-bones-incr"] > 0.22
    assert first["target_weights"]["l-cheek-bones-incr"] == first["target_weights"]["r-cheek-bones-incr"]

    changed_packet = deepcopy(packet)
    for operation in changed_packet["operations"]:
        if operation["parameter"] == "face.nose_width":
            operation["value"] = -0.50
    changed_mesh, _, changed = build_player_face_variant(changed_packet)
    assert changed["mesh_digest"] != first["mesh_digest"]
    assert changed["target_weights"]["nose-width1-incr"] < first["target_weights"]["nose-width1-incr"]
    assert changed_mesh.vertices != first_mesh.vertices
    assert changed_mesh.faces == first_mesh.faces

    zero_weights = semantic_face_to_target_weights({"character": {"face": {"nose_width": -1.0, "cheekbone_strength": -1.0}}})
    assert zero_weights == {
        "nose-width1-incr": 0.0,
        "l-cheek-bones-incr": 0.0,
        "r-cheek-bones-incr": 0.0,
    }

    print("HM08 PLAYER EDIT TEST PASS", {
        "variant": first["edit_variant_digest"],
        "mesh": first["mesh_digest"],
        "targets": first["target_weights"],
    })


if __name__ == "__main__":
    run()
