#!/usr/bin/env python3
from native_geometry import make_uv_sphere, scale
from native_hair import hair_cards_with_uv, validate_hair
from native_hair_roots import generate_short_hair_from_roots
from native_uv import validate_uv


def run() -> None:
    head = scale(make_uv_sphere(1.0, segments=24, rings=12, name="explicit_root_head"), (0.16, 0.22, 0.18))
    candidates = [index for index, point in enumerate(head.vertices) if point[1] > 0.02]
    first = generate_short_hair_from_roots(head, candidates, guide_count=48, segments=5, length=0.022, seed=991)
    second = generate_short_hair_from_roots(head, reversed(candidates), guide_count=48, segments=5, length=0.022, seed=991)
    assert first.root_indices == second.root_indices
    assert len(first.root_indices) == 48
    assert len(set(first.root_indices)) == 48
    assert first.system.guides == second.system.guides
    report = validate_hair(first.system)
    assert report["status"] == "pass", report
    cards, uvmap = hair_cards_with_uv(first.system)
    assert validate_uv(cards, uvmap)["status"] == "pass"

    try:
        generate_short_hair_from_roots(head, candidates[:5], guide_count=6, seed=1)
        raise AssertionError("duplicate-root rejection did not fire")
    except ValueError as exc:
        assert "unique roots" in str(exc)

    print("EXPLICIT ROOT HAIR TEST PASS", {
        "candidates": len(candidates),
        "guides": len(first.root_indices),
        "min_outward_dot": report["min_root_outward_dot"],
        "card_faces": report["card_faces"],
    })


if __name__ == "__main__":
    run()
