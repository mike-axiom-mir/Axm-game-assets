#!/usr/bin/env python3
from native_armor_conform import conform_sentinel_armor
from native_armor_fit_evidence import armor_fit_evidence
from native_geometry import combine
from native_hm08_sentinel_armor import build_sentinel_rigid_armor
from native_hm08_undersuit import _load_identity_body


def run() -> None:
    body_m, _uv, _state = _load_identity_body()
    primary, primary_uv, accent, accent_uv, _armor = build_sentinel_rigid_armor(body_m)
    baseline = armor_fit_evidence(body_m, combine([primary, accent], name="armor_baseline"))

    fitted_primary, fitted_accent, conform = conform_sentinel_armor(body_m, primary, accent)
    fitted = armor_fit_evidence(body_m, combine([fitted_primary, fitted_accent], name="armor_fitted"))

    assert fitted_primary.faces == primary.faces
    assert fitted_accent.faces == accent.faces
    assert len(fitted_primary.vertices) == len(primary.vertices)
    assert len(fitted_accent.vertices) == len(accent.vertices)
    assert conform["primary"]["truth"]["canonical_source_mutated"] is False
    assert conform["accent"]["truth"]["canonical_source_mutated"] is False

    baseline_float = baseline["fractions"]["obviously_floating"]
    fitted_float = fitted["fractions"]["obviously_floating"]
    baseline_median = baseline["signed_normal_offset_m"]["median"]
    fitted_median = fitted["signed_normal_offset_m"]["median"]
    fitted_penetration = fitted["fractions"]["likely_interpenetrating"]

    # v0.1 must solve the measured static-fit failure rather than merely move bytes.
    assert baseline_float > 0.60, baseline
    assert fitted_float < baseline_float * 0.55, (baseline, fitted)
    assert fitted_median < baseline_median * 0.70, (baseline, fitted)
    assert fitted_penetration < 0.10, fitted
    assert fitted["fractions"]["within_intended_clearance"] > baseline["fractions"]["within_intended_clearance"], (baseline, fitted)
    assert conform["primary"]["max_accumulated_move_m"] <= 0.126 + 1e-12
    assert conform["accent"]["max_accumulated_move_m"] <= 0.126 + 1e-12

    # Determinism: same source state and specs produce the same fitted bytes/evidence.
    primary_2, _primary_uv_2, accent_2, _accent_uv_2, _armor_2 = build_sentinel_rigid_armor(body_m)
    fitted_primary_2, fitted_accent_2, conform_2 = conform_sentinel_armor(body_m, primary_2, accent_2)
    assert fitted_primary.vertices == fitted_primary_2.vertices
    assert fitted_accent.vertices == fitted_accent_2.vertices
    assert conform == conform_2

    # UV compatibility is intentional: no indexing changes occur in the conform pass.
    assert len(primary_uv.face_uvs) == len(fitted_primary.faces)
    assert len(accent_uv.face_uvs) == len(fitted_accent.faces)

    print("ARMOR CONFORM TEST PASS", {
        "baseline": {
            "median_signed_mm": baseline_median * 1000.0,
            "obvious_float_fraction": baseline_float,
            "penetration_fraction": baseline["fractions"]["likely_interpenetrating"],
            "intended_fraction": baseline["fractions"]["within_intended_clearance"],
        },
        "fitted": {
            "median_signed_mm": fitted_median * 1000.0,
            "obvious_float_fraction": fitted_float,
            "penetration_fraction": fitted_penetration,
            "intended_fraction": fitted["fractions"]["within_intended_clearance"],
        },
        "primary_max_move_mm": conform["primary"]["max_accumulated_move_m"] * 1000.0,
        "accent_max_move_mm": conform["accent"]["max_accumulated_move_m"] * 1000.0,
    })


if __name__ == "__main__":
    run()
