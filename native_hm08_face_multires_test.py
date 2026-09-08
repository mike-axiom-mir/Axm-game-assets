#!/usr/bin/env python3
from pathlib import Path
from tempfile import TemporaryDirectory

from native_hm08_face_multires import build_face_multires_package


def run() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        package = build_face_multires_package(root, texture_size=64, smoothing_strength=0.10)
        assert all(package["acceptance"].values()), package["acceptance"]
        subdiv = package["subdivision"]
        assert subdiv["source_vertices"] == 4197
        assert subdiv["source_triangles"] == 8336
        assert subdiv["result_triangles"] == 33344
        assert subdiv["result_vertices"] > subdiv["source_vertices"]
        assert subdiv["source_boundary_unchanged"] is True
        assert 0.0 < subdiv["original_vertex_displacement"]["max_mm"] < 3.0
        assert package["uv"]["status"] == "pass"
        assert package["delivery"]["primitive_count"] == 5
        assert package["truth"]["preferred_lod0_claim"] is False
        print("HM08 FACE MULTIRES PACKAGE PASS", subdiv, package["delivery"])


if __name__ == "__main__":
    run()
