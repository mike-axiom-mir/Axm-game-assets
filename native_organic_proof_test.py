#!/usr/bin/env python3
from pathlib import Path
from tempfile import TemporaryDirectory

from native_organic_proof import build_organic_proof


def run() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        proof = build_organic_proof(root, preview_size=64, micro_seed=4401)
        assert all(proof["acceptance"].values()), proof["acceptance"]
        assert proof["truth"]["high_end_face_claim"] is False
        assert proof["seed"]["triangles"] == 224
        assert proof["detail"]["triangles"] == 3584
        assert proof["detail"]["micro_displacement"]["max"] <= 0.0012001
        assert len(proof["targets"]) == 4
        assert len(list((root / "preview-seed").glob("*.png"))) == 9
        assert len(list((root / "preview-variant").glob("*.png"))) == 9
        assert len(list((root / "preview-detail").glob("*.png"))) == 9
        print("NATIVE ORGANIC PROOF PASS", proof["seed"]["triangles"], "->", proof["detail"]["triangles"], proof["acceptance"])


if __name__ == "__main__":
    run()
