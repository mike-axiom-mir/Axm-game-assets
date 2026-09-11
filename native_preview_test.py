#!/usr/bin/env python3
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from native_geometry import Mesh, make_box
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
        root = Path(tmp)
        report = write_preview(high, root, size=64)
        assert len(report["views"]) == 3
        assert len(list(root.glob("*.png"))) == 9
        assert "Aspect-preserving" in report["truth"]
        assert report["review"] == {
            "html": "review.html",
            "report": "preview-report.json",
            "authority": "presentation_only_no_automatic_acceptance",
        }
        assert json.loads((root / "preview-report.json").read_text()) == report
        review = (root / "review.html").read_text()
        assert review.count('class="frame"') == 9
        assert 'data-filter="silhouette"' in review
        assert 'aria-live="polite"' in review
        assert "not engine renders, aesthetic approval, or CANON" in review
        assert "ArrowLeft" in review and "prefers-reduced-motion" in review

        unsafe = root / "unsafe-name"
        write_preview(high.copy(name='<script>alert("asset")</script>'), unsafe, size=32, views=("front",))
        unsafe_review = (unsafe / "review.html").read_text()
        assert '<script>alert("asset")</script>' not in unsafe_review
        assert '&lt;script&gt;alert(&quot;asset&quot;)&lt;/script&gt;' in unsafe_review

        edge = root / "edge-on"
        write_preview(Mesh("edge-on plane", [(-1, 0, -1), (1, 0, -1), (1, 0, 1), (-1, 0, 1)], [(0, 1, 2, 3)]), edge, size=32, views=("side",))
        assert "no covered pixels" in (edge / "review.html").read_text()
    print("NATIVE PREVIEW TEST PASS", low_front["coverage"], high_front["coverage"])


if __name__ == "__main__":
    run()
