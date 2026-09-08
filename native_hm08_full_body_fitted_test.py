#!/usr/bin/env python3
from tempfile import TemporaryDirectory

from native_hm08_full_body_fitted import build_fitted_full_body_package


def run() -> None:
    with TemporaryDirectory() as td:
        package = build_fitted_full_body_package(td, texture_size=64)
    assert all(package["acceptance"].values()), package["acceptance"]
    assert package["schema"] == "axm.game-assets.hm08-full-body-fitted.v0.1"
    assert package["candidate_role"] == "armor_fit_ab_candidate"
    assert package["changed_variable"] == "rigid_armor_static_fit_only"
    assert package["control_builder_schema"] == "axm.game-assets.hm08-full-body-current.v0.4"
    assert package["delivery"]["material_count"] == 14
    assert package["delivery"]["primitive_count"] == 14
    fit = package["armor_fit"]
    assert all(fit["acceptance"].values()), fit
    assert fit["baseline"]["fractions"]["obviously_floating"] > 0.60
    assert fit["fitted"]["fractions"]["obviously_floating"] < 0.02
    assert fit["fitted"]["signed_normal_offset_m"]["median"] < 0.035
    assert fit["fitted"]["fractions"]["likely_interpenetrating"] < 0.05
    assert fit["truth"]["canonical_armor_mutated"] is False
    assert package["truth"]["automatic_visual_promotion"] is False
    print("HM08 FITTED FULL BODY PACKAGE PASS", {
        "baseline_median_mm": fit["baseline"]["signed_normal_offset_m"]["median"] * 1000.0,
        "fitted_median_mm": fit["fitted"]["signed_normal_offset_m"]["median"] * 1000.0,
        "baseline_float_fraction": fit["baseline"]["fractions"]["obviously_floating"],
        "fitted_float_fraction": fit["fitted"]["fractions"]["obviously_floating"],
        "materials": package["delivery"]["material_count"],
    })


if __name__ == "__main__":
    run()
