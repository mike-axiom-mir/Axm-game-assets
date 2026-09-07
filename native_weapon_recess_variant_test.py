#!/usr/bin/env python3
from native_geometry import triangulate
from native_weapon import sentinel_rifle, validate_weapon
from native_weapon_recess_variant import (
    receiver_recess_variant_report,
    sentinel_rifle_recessed,
)


def run() -> None:
    base = sentinel_rifle()
    variant = sentinel_rifle_recessed()
    base_report = validate_weapon(base)
    variant_report = validate_weapon(variant)
    recess_report = receiver_recess_variant_report(variant)

    assert base_report["status"] == "pass", base_report
    assert variant_report["status"] == "pass", variant_report
    assert recess_report["status"] == "pass", recess_report
    assert len(variant.components) == len(base.components)
    assert set(variant.components) == set(base.components)
    assert variant.sockets == base.sockets
    assert "receiver:true_recess" in variant.semantic_features
    assert "receiver:inset_ejection_surface" in variant.semantic_features
    assert len(triangulate(variant.components["receiver"]).faces) > len(
        triangulate(base.components["receiver"]).faces
    )
    assert recess_report["ejection_plate_max_z"] < recess_report["receiver_outer_visible_z"]
    assert recess_report["inset_clearance"] > 0.010
    assert variant.mesh.vertices != base.mesh.vertices
    print(
        "NATIVE WEAPON RECESS VARIANT TEST PASS",
        len(variant.components),
        "components",
        len(triangulate(base.mesh).faces),
        "->",
        len(triangulate(variant.mesh).faces),
        "triangles",
        "clearance",
        recess_report["inset_clearance"],
    )


if __name__ == "__main__":
    run()
