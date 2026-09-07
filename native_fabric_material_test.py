#!/usr/bin/env python3
from pathlib import Path
from tempfile import TemporaryDirectory

from native_fabric_material import fabric_fields, write_fabric_material


def run() -> None:
    a = fabric_fields(64, 91)
    b = fabric_fields(64, 91)
    c = fabric_fields(64, 92)
    assert a == b
    assert a != c
    assert set(a) == {"base_color", "roughness", "height", "normal", "ao", "thickness", "orm"}
    assert a["normal"][0] == 3 and a["orm"][0] == 3
    orm = a["orm"][1]
    assert all(orm[index + 2] == 0 for index in range(0, len(orm), 3))

    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        material = write_fabric_material(root, size=64, seed=91)
        assert material["renderer_hints"]["two_sided"] is True
        assert material["truth"]["physically_measured"] is False
        assert material["truth"]["deterministic"] is True
        assert len(material["maps"]) == 7
        assert len(list(root.glob("*.png"))) == 7
        assert (root / "fabric-material.json").exists()
        print("NATIVE FABRIC MATERIAL TEST PASS", material["manifest_sha256"], len(material["maps"]), "maps")


if __name__ == "__main__":
    run()
