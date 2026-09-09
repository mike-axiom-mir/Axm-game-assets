#!/usr/bin/env python3
from pathlib import Path
from tempfile import TemporaryDirectory

from native_geometry import make_box
from native_hardsurface import sentinel_armor_plate
from native_preview import render, write_preview


def run() -> None:
    low, _ = sentinel_armor_plate(0)
    high, _ = sentinel_armor_plate(3)
    low_front = render(low, view="front", size=64)
    high_front = render(high, view="front", size=64)
    assert low_front["covered_pixels"] > 0 and high_front["covered_pixels"] > 0
    assert low_front["hashes"]["depth"] != high_front["hashes"]["depth"]
    low_side = render(low, view="side", size=64)
    high_side = render(high, view="side", size=64)
    assert low_side["hashes"]["silhouette"] != high_side["hashes"]["silhouette"]
    assert low_side["hashes"]["normal"] != high_side["hashes"]["normal"]

    tall = render(make_box((1.0, 4.0, 1.0), name="tall_box"), view="front", size=128, margin=0.1)
    projection = tall["projection"]
    bounds = projection["content_bounds_px"]
    assert projection["fit"] == "contain" and projection["aspect_preserved"] is True
    assert 3.8 <= bounds["height"] / bounds["width"] <= 4.2, bounds
    assert abs(bounds["left"] - (127 - bounds["right"])) <= 2, bounds
    assert abs(bounds["top"] - (127 - bounds["bottom"])) <= 2, bounds

    with TemporaryDirectory() as tmp:
        report = write_preview(high, Path(tmp), size=64)
        assert len(report["views"]) == 3
        assert len(list(Path(tmp).glob("*.png"))) == 9
        assert "Aspect-preserving" in report["truth"]
    print("NATIVE PREVIEW TEST PASS", low_front["coverage"], high_front["coverage"])


if __name__ == "__main__":
    run()
