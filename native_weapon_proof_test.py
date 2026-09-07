#!/usr/bin/env python3
from pathlib import Path
from tempfile import TemporaryDirectory

from native_weapon_proof import build_weapon_proof


def run() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        proof = build_weapon_proof(root, texture_size=32, preview_size=64, seed=8801)
        assert all(proof["acceptance"].values()), proof["acceptance"]
        assert proof["truth"]["production_weapon_art_claim"] is False
        assert proof["truth"]["ballistics_claim"] is False
        assert proof["two_hand_contact"]["max_primary_position_error"] < 1e-8
        assert proof["two_hand_contact"]["max_support_position_error"] < 1e-8
        assert "muzzle" in proof["sockets"]
        assert proof["delivery"]["material_name"] == "AXM_Native_Weapon_Metal"
        assert len(list((root / "preview").glob("*.png"))) == 9
        assert (root / "weapon-proof.json").exists()
        print("NATIVE WEAPON PROOF PASS", proof["weapon"]["components"], "components", proof["weapon"]["triangles"], "triangles")


if __name__ == "__main__":
    run()
