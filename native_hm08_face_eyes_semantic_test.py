#!/usr/bin/env python3
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from native_hm08_face_eyes import build_face_eyes_package


def run() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        package = build_face_eyes_package(root, texture_size=32, skin_mode="semantic_v0.1")
        assert all(package["acceptance"].values()), package["acceptance"]
        assert package["skin_mode"] == "semantic_v0.1"
        assert package["skin"]["schema"] == "axm.game-assets.hm08-semantic-skin.v0.1"
        assert package["skin"]["truth"]["semantic_regions_source"].startswith("derived from canonical hm08")
        assert package["skin"]["evidence"]["landmarks"]["mouth_boundary_vertices"] == 12
        assert package["delivery"]["primitive_count"] == 5
        assert package["delivery"]["material_count"] == 5
        assert package["delivery"]["material_names"][0] == "AXM_Sentinel_Skin_Semantic_v0_1"
        assert package["truth"]["high_end_skin_claim"] is False
        document = json.loads((root / package["delivery"]["gltf"]).read_text())
        assert document["materials"][0]["pbrMetallicRoughness"]["metallicFactor"] == 0.0
        assert document["materials"][4]["alphaMode"] == "BLEND"
        print(
            "HM08 FACE EYES SEMANTIC SKIN PASS",
            package["skin"]["evidence"]["coverage"],
            package["skin"]["evidence"]["region_max"],
            package["delivery"]["gltf"],
        )


if __name__ == "__main__":
    run()
