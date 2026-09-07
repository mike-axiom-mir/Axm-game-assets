#!/usr/bin/env python3
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from native_weapon_multimat import GROUP_ORDER
from native_weapon_recess_multimat import build_recessed_weapon_multimat_package


def run() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        package = build_recessed_weapon_multimat_package(root, texture_size=16, seed=8801)
        assert all(package["acceptance"].values()), package["acceptance"]
        assert package["truth"]["preferred_route_claim"] is False
        assert package["variant"] == "receiver_true_recess_v0.1"
        assert package["recess_state"]["status"] == "pass"
        assert package["recess_state"]["inset_clearance"] > 0.010
        assert package["delivery"]["primitive_count"] == 4
        assert package["delivery"]["material_count"] == 4
        assert package["delivery"]["triangles"] == sum(
            package["groups"][group]["triangles"] for group in GROUP_ORDER
        )
        assert tuple(package["groups"].keys()) == GROUP_ORDER
        assert (root / "sentinel_rifle_recessed_multimat.gltf").exists()
        assert (root / "weapon-recess-multimat.json").exists()
        document = json.loads((root / "sentinel_rifle_recessed_multimat.gltf").read_text())
        assert len(document["meshes"][0]["primitives"]) == 4
        assert len(document["materials"]) == 4
        print(
            "NATIVE WEAPON RECESS MULTIMAT TEST PASS",
            package["delivery"]["triangles"],
            "triangles",
            "clearance",
            package["recess_state"]["inset_clearance"],
        )


if __name__ == "__main__":
    run()
