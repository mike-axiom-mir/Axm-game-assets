#!/usr/bin/env python3
from math import cos, pi, sin

from native_character_state import SCHEMA, audit_character_state, from_dict
from native_geometry import Mesh


def packet(max_drift=0.0001):
    half = pi * 0.5
    return {
        "schema": SCHEMA,
        "asset_id": "sentinel-state-fixture",
        "skeleton": {"joints": [
            {"name": "root"},
            {"name": "hand", "parent": 0, "translation": [0.0, 1.0, 0.0]},
        ]},
        "skin": {
            "joints": [[0,0,0,0], [1,0,0,0], [1,0,0,0]],
            "weights": [[1.0,0.0,0.0,0.0], [1.0,0.0,0.0,0.0], [1.0,0.0,0.0,0.0]],
        },
        "morph_targets": [{"name": "scar_raise", "position_deltas": [[0.0,0.0,0.0], [0.0,0.0,0.01], [0.0,0.0,0.0]]}],
        "animations": [{"name": "hand_swing", "tracks": [{
            "joint": 1,
            "path": "rotation",
            "times": [0.0, 1.0],
            "values": [[0.0,0.0,0.0,1.0], [0.0,0.0,sin(half/2.0),cos(half/2.0)]],
        }]}],
        "contacts": [{"id": "root_planted", "animation": "hand_swing", "vertices": [0], "sample_times": [0.0,0.5,1.0], "max_drift": max_drift}],
        "provenance": {"fixture": True},
    }


def run():
    mesh = Mesh("fixture", [(0.0,0.0,0.0), (0.0,2.0,0.0), (0.2,2.0,0.0)], [(0,1,2)])
    state = from_dict(packet())
    report = audit_character_state(state, mesh)
    assert report["status"] == "pass", report
    assert report["counts"]["pass"] == 5

    bad = packet()
    bad["contacts"][0] = {"id":"hand_wrongly_planted", "animation":"hand_swing", "vertices":[1,2], "sample_times":[0.0,0.5,1.0], "max_drift":0.01}
    bad_report = audit_character_state(from_dict(bad), mesh)
    assert bad_report["status"] == "fail"
    contact = next(g for g in bad_report["gates"] if g["gate"] == "contact:hand_wrongly_planted")
    assert contact["evidence"]["max_drift"] > 1.0
    print("NATIVE CHARACTER STATE TEST PASS", report["counts"], "bad drift", contact["evidence"]["max_drift"])


if __name__ == "__main__":
    run()
