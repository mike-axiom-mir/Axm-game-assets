#!/usr/bin/env python3
from pathlib import Path
from tempfile import TemporaryDirectory

from native_hair_proof import build_hair_proof


def run() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        proof = build_hair_proof(root, guide_count=64, segments=6, seed=731, texture_size=32, preview_size=64)
        assert all(proof["acceptance"].values()), proof["acceptance"]
        assert proof["truth"]["high_end_groom_claim"] is False
        assert proof["coverage"]["max_root_to_head"] < 0.003
        assert proof["delivery"]["alpha_mode"] == "MASK"
        assert proof["delivery"]["double_sided"] is True
        assert len(list((root / "preview-bare").glob("*.png"))) == 9
        assert len(list((root / "preview-hair").glob("*.png"))) == 9
        assert (root / "hair-proof.json").exists()
        print("NATIVE HAIR PROOF PASS", proof["hair"]["guides"], "guides", proof["coverage"], proof["delivery"]["triangles"], "triangles")


if __name__ == "__main__":
    run()
