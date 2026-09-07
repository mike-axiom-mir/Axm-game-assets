#!/usr/bin/env python3
from pathlib import Path
from tempfile import TemporaryDirectory

from native_skin_material import SkinMaterialSpec, skin_fields, write_skin_material


def run() -> None:
    a = skin_fields(32, 77)
    b = skin_fields(32, 77)
    c = skin_fields(32, 78)
    assert a == b
    assert a != c
    assert set(a) == {"base_color", "roughness", "height", "normal", "ao", "subsurface_mask", "thickness", "orm"}
    assert a["base_color"][0] == 3 and a["normal"][0] == 3 and a["orm"][0] == 3
    orm = a["orm"][1]
    assert all(orm[index + 2] == 0 for index in range(0, len(orm), 3))

    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        material = write_skin_material(root, size=32, seed=77, spec=SkinMaterialSpec())
        assert material["truth"]["physically_measured"] is False
        assert material["truth"]["human_scan"] is False
        assert material["openpbr_hints"]["base_metalness"] == 0.0
        assert len(material["maps"]) == 8
        assert len(list(root.glob("*.png"))) == 8
        assert (root / "skin-material.json").exists()
        print("NATIVE SKIN MATERIAL TEST PASS", material["manifest_sha256"], len(material["maps"]), "maps")


if __name__ == "__main__":
    run()
