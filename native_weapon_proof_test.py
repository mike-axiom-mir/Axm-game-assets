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
        assert proof["truth"]["material_scan_claim"] is False
        assert proof["two_hand_contact"]["max_primary_position_error"] < 1e-8
        assert proof["two_hand_contact"]["max_support_position_error"] < 1e-8
        assert "muzzle" in proof["sockets"]
        assert proof["delivery"]["material_name"] == "AXM_Native_Weapon_CoatedMetal"
        assert proof["weapon"]["components"] >= 45
        assert proof["weapon"]["triangles"] >= 2000
        assert all(report["status"] == "pass" for report in proof["weapon"]["winding_reports"].values())
        assert proof["material"]["spec"]["paint_roughness"] == 0.64
        assert proof["material"]["spec"]["wear"] == 0.16
        assert len(list((root / "preview").glob("*.png"))) == 9
        assert (root / "weapon-proof.json").exists()
        print(
            "NATIVE WEAPON PROOF PASS",
            proof["weapon"]["components"],
            "components",
            proof["weapon"]["triangles"],
            "triangles",
            proof["delivery"]["material_name"],
        )


if __name__ == "__main__":
    run()
