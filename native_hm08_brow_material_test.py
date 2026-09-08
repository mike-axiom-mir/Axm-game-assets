#!/usr/bin/env python3
from pathlib import Path
from tempfile import TemporaryDirectory

from native_hm08_brow_material import BrowMaterialSpec, brow_card_fields, write_brow_material


def run() -> None:
    spec = BrowMaterialSpec(
        root_rgb=(29, 21, 18),
        tip_rgb=(43, 31, 25),
        density=0.58,
        roughness=0.58,
        filament_contrast=0.18,
    )
    first_fields, first_evidence = brow_card_fields(64, 52081, spec)
    second_fields, second_evidence = brow_card_fields(64, 52081, spec)
    assert first_fields == second_fields
    assert first_evidence == second_evidence
    assert first_evidence["mean_alpha"] > 0.20, first_evidence
    assert first_evidence["max_alpha"] > 0.45, first_evidence
    assert first_evidence["fraction_alpha_ge_0_10"] > 0.70, first_evidence
    assert first_evidence["fraction_alpha_ge_0_25"] > 0.45, first_evidence

    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        first = write_brow_material(root / "a", size=64, seed=52081, spec=spec)
        second = write_brow_material(root / "b", size=64, seed=52081, spec=spec)
        assert first["schema"] == "axm.game-assets.brow-density-material.v0.1"
        assert first["coverage_evidence"] == second["coverage_evidence"]
        assert {name: item["sha256"] for name, item in first["maps"].items()} == {
            name: item["sha256"] for name, item in second["maps"].items()
        }
        assert first["renderer_hints"]["alpha_mode"] == "BLEND"
        assert first["renderer_hints"]["metalness"] == 0.0
        assert first["truth"]["preferred_brow_claim"] is False
        print("HM08 BROW MATERIAL TEST PASS", first["coverage_evidence"])


if __name__ == "__main__":
    run()
