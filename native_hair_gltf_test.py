#!/usr/bin/env python3
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from native_geometry import make_uv_sphere, scale
from native_hair import generate_short_hair, hair_cards_with_uv
from native_hair_gltf import write_hair_gltf
from native_hair_material import write_hair_material


def run() -> None:
    head = scale(make_uv_sphere(1.0, segments=20, rings=10, name="hair_gltf_head"), (0.16, 0.22, 0.18))
    system = generate_short_hair(head, guide_count=32, segments=5, seed=411)
    cards, uvmap = hair_cards_with_uv(system, name="sentinel_short_hair")
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        write_hair_material(root / "textures", size=64, seed=411)
        result = write_hair_gltf(cards, uvmap, root, alpha_cutoff=0.34)
        assert result["validation"]["status"] == "pass"
        assert result["alpha_mode"] == "MASK"
        assert result["double_sided"] is True
        assert result["metallic_factor"] == 0.0
        document = json.loads((root / result["gltf"]).read_text())
        material = document["materials"][0]
        assert material["alphaMode"] == "MASK"
        assert material["doubleSided"] is True
        assert material["pbrMetallicRoughness"]["baseColorTexture"]["index"] == 0
        assert material["pbrMetallicRoughness"]["metallicRoughnessTexture"]["index"] == 1
        assert material["pbrMetallicRoughness"]["metallicFactor"] == 0.0
        assert "TANGENT" in document["meshes"][0]["primitives"][0]["attributes"]
        assert result["triangles"] == 32 * 4 * 2
        print("NATIVE HAIR GLTF TEST PASS", result["triangles"], "triangles", result["compiled_vertices"], "compiled verts", "metallic", result["metallic_factor"])


if __name__ == "__main__":
    run()
