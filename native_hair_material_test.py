#!/usr/bin/env python3
from pathlib import Path
from tempfile import TemporaryDirectory

from native_hair_material import hair_card_fields, write_hair_material


def run() -> None:
    a = hair_card_fields(64, 77)
    b = hair_card_fields(64, 77)
    c = hair_card_fields(64, 78)
    assert a == b
    assert a != c
    assert set(a) == {"base_color_alpha", "alpha", "roughness"}
    assert a["base_color_alpha"][0] == 4
    alpha = a["alpha"][1]
    assert min(alpha) == 0
    assert max(alpha) > 150
    assert len(set(alpha)) > 8

    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        material = write_hair_material(root, size=64, seed=77)
        assert material["renderer_hints"]["two_sided"] is True
        assert material["truth"]["physically_measured"] is False
        assert material["truth"]["deterministic"] is True
        assert len(material["maps"]) == 3
        assert len(list(root.glob("*.png"))) == 3
        assert (root / "hair-material.json").exists()
        print("NATIVE HAIR MATERIAL TEST PASS", material["manifest_sha256"], min(alpha), max(alpha))


if __name__ == "__main__":
    run()
