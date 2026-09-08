#!/usr/bin/env python3
from pathlib import Path
from tempfile import TemporaryDirectory

from native_hm08_face_proof import build_hm08_face_proof


def run() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        proof = build_hm08_face_proof(root, texture_size=32, preview_size=64, seed=20801)
        assert all(proof["acceptance"].values()), proof["acceptance"]
        assert proof["seed_basemesh"] == "axm-hm08-head-v0.2"
        assert proof["truth"]["human_topology"] is True
        assert proof["truth"]["high_end_face_claim"] is False
        assert proof["displacement"]["moved_vertices"] >= 100
        assert proof["delivery"]["validation"]["status"] == "pass"
        assert proof["delivery"]["triangles"] == 8336
        assert len(list((root / "preview" / "base").glob("*.png"))) == 9
        assert len(list((root / "preview" / "variant").glob("*.png"))) == 9
        assert (root / "source" / "base-head.obj").exists()
        assert (root / "source" / "sentinel-face-candidate.obj").exists()
        assert (root / "hm08-face-proof.json").exists()
        print(
            "HM08 FACE PROOF PASS",
            proof["displacement"],
            proof["diagnostic_signal_changes"],
            proof["delivery"]["gltf_sha256"],
        )


if __name__ == "__main__":
    run()
