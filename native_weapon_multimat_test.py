#!/usr/bin/env python3
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from native_weapon_multimat import GROUP_ORDER, build_weapon_multimat_package, component_group


def run() -> None:
    assert component_group("stock_core") == "polymer"
    assert component_group("barrel") == "steel"
    assert component_group("optic_body") == "accessory"
    assert component_group("receiver") == "coated"
    assert component_group("upper_rail_tooth_05") == "accessory"
    assert component_group("fastener_left_03") == "steel"

    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        package = build_weapon_multimat_package(root, texture_size=16, seed=8801)
        assert all(package["acceptance"].values()), package["acceptance"]
        assert tuple(package["groups"].keys()) == GROUP_ORDER
        assert package["delivery"]["primitive_count"] == 4
        assert package["delivery"]["material_count"] == 4
        assert package["delivery"]["triangles"] == package["source_weapon"]["triangles"]
        assert package["groups"]["polymer"]["metallic_factor"] == 0.0
        assert package["groups"]["polymer"]["component_count"] >= 8
        assert package["groups"]["steel"]["component_count"] >= 10
        assert package["groups"]["accessory"]["component_count"] >= 10
        assert package["groups"]["coated"]["component_count"] >= 5
        assert (root / "sentinel_rifle_multimat.gltf").exists()
        assert (root / "weapon-multimat.json").exists()
        document = json.loads((root / "sentinel_rifle_multimat.gltf").read_text())
        assert len(document["meshes"][0]["primitives"]) == 4
        assert len(document["materials"]) == 4
        print(
            "NATIVE WEAPON MULTIMAT TEST PASS",
            package["delivery"]["triangles"],
            "triangles",
            {group: package["groups"][group]["component_count"] for group in GROUP_ORDER},
        )


if __name__ == "__main__":
    run()
