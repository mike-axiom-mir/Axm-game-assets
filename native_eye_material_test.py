#!/usr/bin/env python3
from pathlib import Path
from tempfile import TemporaryDirectory

from native_eye_material import iris_fields, sclera_fields, write_eye_material


def run() -> None:
    iris_a = iris_fields(32, 44)
    iris_b = iris_fields(32, 44)
    iris_c = iris_fields(32, 45)
    assert iris_a == iris_b
    assert iris_a != iris_c
    assert set(iris_a) == {"iris_base_color", "iris_roughness", "iris_normal", "iris_mask"}
    sclera_a = sclera_fields(32, 44)
    sclera_b = sclera_fields(32, 44)
    assert sclera_a == sclera_b
    assert set(sclera_a) == {"sclera_base_color", "sclera_roughness", "sclera_normal"}

    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        material = write_eye_material(root, size=32, seed=44)
        assert material["truth"]["physically_measured"] is False
        assert material["layers"]["cornea"]["openpbr_transmission_weight_hint"] == 1.0
        assert len(material["maps"]) == 7
        assert len(list(root.glob("*.png"))) == 7
        assert (root / "eye-material.json").exists()
        print("NATIVE EYE MATERIAL TEST PASS", material["manifest_sha256"], len(material["maps"]), "maps")


if __name__ == "__main__":
    run()
