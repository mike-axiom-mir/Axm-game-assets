#!/usr/bin/env python3
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from native_hm08_face_secondary import build_face_secondary_package


def run() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        package = build_face_secondary_package(root, texture_size=32)
        assert all(package["acceptance"].values()), package["acceptance"]
        assert package["ab_variable"] == "secondary_facial_geometry_only"
        assert package["ab_control"]["skin_mode"] == "generic"
        assert len(package["secondary_forms"]["target_rows"]) == 12
        assert all(rows > 0 for rows in package["secondary_forms"]["target_rows"].values())
        assert package["secondary_forms"]["displacement"]["max_distance_mm"] < 4.0
        assert package["secondary_forms"]["displacement"]["moved_vertices"] > 100
        assert package["delivery"]["primitive_count"] == 5
        assert package["delivery"]["material_names"] == [
            "AXM_Sentinel_Skin_Prototype",
            "AXM_Eye_Sclera",
            "AXM_Eye_Iris",
            "AXM_Eye_Pupil",
            "AXM_Eye_Cornea_Prototype",
        ]
        assert package["truth"]["aesthetic_improvement_claim"] is False
        document = json.loads((root / package["delivery"]["gltf"]).read_text())
        assert len(document["meshes"][0]["primitives"]) == 5
        assert document["materials"][0]["pbrMetallicRoughness"]["metallicFactor"] == 0.0
        print(
            "HM08 FACE SECONDARY PACKAGE PASS",
            package["secondary_forms"]["displacement"],
            package["secondary_forms"]["target_rows"],
            package["delivery"]["gltf"],
        )


if __name__ == "__main__":
    run()
