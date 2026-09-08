#!/usr/bin/env python3
from native_armor_fit_evidence import armor_fit_evidence
from native_geometry import combine
from native_hm08_sentinel_armor import build_sentinel_rigid_armor
from native_hm08_undersuit import _load_identity_body


def run() -> None:
    body_m, _uv, _state = _load_identity_body()
    primary_a, _uv_a, accent_a, _uv_accent_a, armor_state_a = build_sentinel_rigid_armor(body_m)
    primary_b, _uv_b, accent_b, _uv_accent_b, armor_state_b = build_sentinel_rigid_armor(body_m)
    assert armor_state_a == armor_state_b
    armor_a = combine([primary_a, accent_a], name="sentinel_armor_fit_subject")
    armor_b = combine([primary_b, accent_b], name="sentinel_armor_fit_subject")
    first = armor_fit_evidence(body_m, armor_a)
    second = armor_fit_evidence(body_m, armor_b)
    assert first == second
    assert first["schema"] == "axm.game-assets.armor-fit-evidence.v0.1"
    assert first["sample_count"] == len(armor_a.vertices) > 0
    assert first["body_vertex_count"] == 13380
    assert first["fallback_queries"] == 0
    assert first["nearest_distance_m"]["max"] >= first["nearest_distance_m"]["p95"] >= first["nearest_distance_m"]["median"] >= 0.0
    assert first["signed_normal_offset_m"]["max"] >= first["signed_normal_offset_m"]["median"]
    assert all(0.0 <= value <= 1.0 for value in first["fractions"].values())
    assert first["truth"]["production_fit_claim"] is False
    print("ARMOR FIT EVIDENCE PASS", first)


if __name__ == "__main__":
    run()
