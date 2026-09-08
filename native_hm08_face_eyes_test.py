#!/usr/bin/env python3
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from native_hm08_face_eyes import build_face_eyes_package


def run() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        package = build_face_eyes_package(root, texture_size=32)
        assert all(package["acceptance"].values()), package["acceptance"]
        assert package["coordinate_conversion"] == {"source_unit":"decimeter","delivery_unit":"meter","scale":0.1}
        assert package["delivery"]["primitive_count"] == 5
        assert package["delivery"]["material_count"] == 5
        assert package["delivery"]["validation"]["status"] == "pass"
        assert package["truth"]["high_end_eye_claim"] is False
        assert package["truth"]["corneal_refraction_claim"] is False
        document = json.loads((root / package["delivery"]["gltf"]).read_text())
        names = [material["name"] for material in document["materials"]]
        assert names == [
            "AXM_Sentinel_Skin_Prototype",
            "AXM_Eye_Sclera",
            "AXM_Eye_Iris",
            "AXM_Eye_Pupil",
            "AXM_Eye_Cornea_Prototype",
        ]
        cornea = document["materials"][4]
        assert cornea["alphaMode"] == "BLEND"
        assert cornea["pbrMetallicRoughness"]["baseColorFactor"][3] == 0.12
        assert package["eye_landmarks"]["eyes"]["left"]["center_m"][0] > 0
        assert package["eye_landmarks"]["eyes"]["right"]["center_m"][0] < 0
        assert abs(package["eye_landmarks"]["prototype_eye_radius_m"] - 0.013815) < 1e-12
        print("HM08 FACE EYES PACKAGE PASS", package["delivery"], package["eye_landmarks"]["eyes"])


if __name__ == "__main__":
    run()
