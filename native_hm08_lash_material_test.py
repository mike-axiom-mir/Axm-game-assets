#!/usr/bin/env python3
from pathlib import Path
from tempfile import TemporaryDirectory

from native_hm08_lash_material import LashMaterialSpec, lash_ribbon_fields, write_lash_material


def run() -> None:
    spec = LashMaterialSpec(root_rgb=(17, 12, 10), tip_rgb=(29, 20, 16), density=0.78, roughness=0.54)
    first_fields, first_evidence = lash_ribbon_fields(64, 62081, spec)
    second_fields, second_evidence = lash_ribbon_fields(64, 62081, spec)
    assert first_fields == second_fields
    assert first_evidence == second_evidence
    assert first_evidence["mean_alpha"] > 0.20, first_evidence
    assert first_evidence["max_alpha"] > 0.60, first_evidence
    assert first_evidence["fraction_alpha_ge_0_10"] > 0.55, first_evidence
    assert first_evidence["fraction_alpha_ge_0_35"] > 0.30, first_evidence

    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        first = write_lash_material(root / "a", size=64, seed=62081, spec=spec)
        second = write_lash_material(root / "b", size=64, seed=62081, spec=spec)
        assert first["schema"] == "axm.game-assets.lash-ribbon-material.v0.1"
        assert first["coverage_evidence"] == second["coverage_evidence"]
        assert {name: item["sha256"] for name, item in first["maps"].items()} == {
            name: item["sha256"] for name, item in second["maps"].items()
        }
        assert first["renderer_hints"]["alpha_mode"] == "BLEND"
        assert first["renderer_hints"]["metalness"] == 0.0
        assert first["truth"]["preferred_lash_claim"] is False
        print("HM08 LASH MATERIAL TEST PASS", first["coverage_evidence"])


if __name__ == "__main__":
    run()
