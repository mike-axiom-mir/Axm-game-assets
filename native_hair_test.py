#!/usr/bin/env python3
from native_geometry import make_uv_sphere, scale
from native_hair import generate_short_hair, hair_cards, hair_cards_with_uv, validate_hair
from native_uv import validate_uv


def run() -> None:
    head = scale(make_uv_sphere(1.0, segments=20, rings=10, name="head_for_hair"), (0.16, 0.22, 0.18))
    a = generate_short_hair(head, guide_count=48, segments=5, seed=77)
    b = generate_short_hair(head, guide_count=48, segments=5, seed=77)
    c = generate_short_hair(head, guide_count=48, segments=5, seed=78)
    assert a.guides[0].points == b.guides[0].points
    assert a.guides[0].points != c.guides[0].points
    report = validate_hair(a)
    assert report["status"] == "pass", report
    cards = hair_cards(a)
    cards_uv, uvmap = hair_cards_with_uv(a)
    assert cards.vertices == cards_uv.vertices and cards.faces == cards_uv.faces
    assert len(cards.faces) == 48 * 4
    assert len(cards.vertices) == 48 * 10
    assert validate_uv(cards_uv, uvmap)["status"] == "pass"
    assert len(uvmap.uvs) == len(cards.vertices)
    assert uvmap.uvs[0] == (0.0, 0.0) and uvmap.uvs[1] == (1.0, 0.0)
    assert uvmap.uvs[8] == (0.0, 1.0) and uvmap.uvs[9] == (1.0, 1.0)
    assert all(guide.root_width > guide.tip_width for guide in a.guides)
    print("NATIVE HAIR TEST PASS", report["guides"], "guides", report["card_faces"], "card faces", report["uvs"], "uvs")


if __name__ == "__main__":
    run()
