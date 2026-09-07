#!/usr/bin/env python3
from native_cloth import SphereCollider, cloth_evidence, copy_cloth, make_cloth_grid, simulate_cloth


def run() -> None:
    collider = SphereCollider((0.0, 0.0, 0.0), 0.22)
    a = make_cloth_grid(0.8, 0.8, columns=12, rows=12, height=0.55)
    b = copy_cloth(a)
    simulate_cloth(a, steps=120, dt=1.0 / 60.0, iterations=10, colliders=[collider])
    simulate_cloth(b, steps=120, dt=1.0 / 60.0, iterations=10, colliders=[collider])
    assert a.positions == b.positions

    evidence = cloth_evidence(a, colliders=[collider])
    assert evidence["max_pin_drift"] == 0.0
    assert evidence["max_sphere_penetration"] < 1e-8
    assert evidence["max_constraint_strain"] < 0.04, evidence
    assert evidence["bounds_y"][0] < 0.0
    assert evidence["pins"] == 13
    assert evidence["constraints"] > 800

    different = make_cloth_grid(0.8, 0.8, columns=12, rows=12, height=0.55)
    different.gravity = (2.0, -9.81, 0.0)
    simulate_cloth(different, steps=120, dt=1.0 / 60.0, iterations=10, colliders=[collider])
    assert different.positions != a.positions
    print(
        "NATIVE CLOTH TEST PASS",
        evidence["vertices"], "vertices",
        evidence["constraints"], "constraints",
        "max strain", evidence["max_constraint_strain"],
        "penetration", evidence["max_sphere_penetration"],
    )


if __name__ == "__main__":
    run()
