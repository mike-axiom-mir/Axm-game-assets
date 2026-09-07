#!/usr/bin/env python3
from native_geometry import make_uv_sphere, scale
from native_hair import generate_short_hair, hair_cards, validate_hair


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
    assert len(cards.faces) == 48 * 4
    assert len(cards.vertices) == 48 * 10
    assert all(guide.root_width > guide.tip_width for guide in a.guides)
    print("NATIVE HAIR TEST PASS", report["guides"], "guides", report["card_faces"], "cards faces")


if __name__ == "__main__":
    run()
