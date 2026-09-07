#!/usr/bin/env python3
from pathlib import Path
from tempfile import TemporaryDirectory

from native_cloth_proof import build_cloth_proof


def run() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        proof = build_cloth_proof(root, steps=120, seed=515, texture_size=32, preview_size=64)
        assert all(proof["acceptance"].values()), proof["acceptance"]
        assert proof["truth"]["production_garment_claim"] is False
        evidence = proof["simulation"]["evidence"]
        assert evidence["max_pin_drift"] == 0.0
        assert evidence["max_constraint_strain"] < 0.04
        assert proof["delivery"]["material_name"] == "AXM_Native_WovenFabric"
        assert proof["delivery"]["double_sided"] is True
        assert len(list((root / "preview-rest").glob("*.png"))) == 9
        assert len(list((root / "preview-final").glob("*.png"))) == 9
        assert (root / "cloth-proof.json").exists()
        print("NATIVE CLOTH PROOF PASS", evidence["vertices"], "vertices", evidence["max_constraint_strain"], "max strain")


if __name__ == "__main__":
    run()
