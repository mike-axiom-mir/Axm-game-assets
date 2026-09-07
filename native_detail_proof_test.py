#!/usr/bin/env python3
from pathlib import Path
from tempfile import TemporaryDirectory

from native_detail_proof import build_detail_proof


def run() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        proof = build_detail_proof(root, texture_size=32, preview_size=64, seed=6007)
        assert all(proof["acceptance"].values())
        triangles = [level["triangles"] for level in proof["levels"]]
        components = [level["components"] for level in proof["levels"]]
        assert triangles == [28, 112, 428, 732]
        assert components == [1, 4, 13, 21]
        assert proof["blender_required"] is False
        assert proof["truth"]["high_end_character_claim"] is False
        assert "automatically higher quality" in proof["diagnostic_signal_notes"]["interpretation"]
        for level in range(4):
            preview_dir = root / f"lod_source_detail_{level}" / "preview"
            assert len(list(preview_dir.glob("*.png"))) == 9
        print("NATIVE DETAIL PROOF PASS", triangles, components, proof["acceptance"])


if __name__ == "__main__":
    run()
