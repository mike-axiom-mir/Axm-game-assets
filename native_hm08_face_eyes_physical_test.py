#!/usr/bin/env python3
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from native_hm08_face_eyes import build_face_eyes_package


def run() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        package = build_face_eyes_package(root, texture_size=64, skin_mode="physical_v0.1")
        assert all(package["acceptance"].values()), package["acceptance"]
        assert package["skin_mode"] == "physical_v0.1"
        assert package["skin"]["schema"] == "axm.game-assets.hm08-physical-skin.v0.1"
        assert package["skin"]["truth"]["noise_coordinate_space"].startswith("canonical 3D hm08")
        assert package["skin"]["evidence"]["landmarks"]["mouth_center"][1] > 6.55
        assert package["delivery"]["primitive_count"] == 5
        assert package["delivery"]["material_names"][0] == "AXM_Sentinel_Skin_Physical_v0_1"
        assert package["truth"]["high_end_skin_claim"] is False
        document = json.loads((root / package["delivery"]["gltf"]).read_text())
        assert document["materials"][0]["pbrMetallicRoughness"]["metallicFactor"] == 0.0
        assert document["materials"][4]["alphaMode"] == "BLEND"
        print("HM08 FACE EYES PHYSICAL SKIN PASS", package["skin"]["evidence"], package["delivery"]["gltf"])


if __name__ == "__main__":
    run()
