#!/usr/bin/env python3
from native_geometry import bounds, topology_report, triangulate
from native_orientation import winding_report
from native_recess import make_recessed_box, recess_report


def run() -> None:
    mesh = make_recessed_box(
        0.50,
        0.155,
        0.105,
        recess_width=0.16,
        recess_height=0.065,
        recess_depth=0.018,
        recess_center=(0.075, 0.010),
        name="receiver_recess_fixture",
    )
    topology = topology_report(mesh)
    winding = winding_report(mesh)
    report = recess_report(mesh)
    assert topology["closed_two_manifold_candidate"], topology
    assert topology["boundary_edges"] == 0
    assert topology["nonmanifold_edges"] == 0
    assert winding["status"] == "pass", winding
    assert winding["classification"] == "outward"
    assert report["status"] == "pass", report
    lo, hi = bounds(mesh)
    assert lo == (-0.25, -0.0775, -0.0525)
    assert hi == (0.25, 0.0775, 0.0525)
    assert len(triangulate(mesh).faces) > 12

    # Recess depth changes internal geometry while preserving the same outer AABB.
    deeper = make_recessed_box(
        0.50,
        0.155,
        0.105,
        recess_width=0.16,
        recess_height=0.065,
        recess_depth=0.030,
        recess_center=(0.075, 0.010),
        name="receiver_recess_deeper",
    )
    assert bounds(deeper) == (lo, hi)
    assert deeper.vertices != mesh.vertices

    # 0.49 inside a 0.50 shell is still mathematically valid and leaves a
    # 5 mm border on each side. The rejection fixture must actually touch/cross
    # the outer boundary rather than encode an unstated aesthetic minimum.
    rejected = False
    try:
        make_recessed_box(
            0.50,
            0.155,
            0.105,
            recess_width=0.50,
            recess_height=0.10,
            recess_depth=0.018,
        )
    except ValueError:
        rejected = True
    assert rejected
    print(
        "NATIVE RECESS TEST PASS",
        len(mesh.vertices),
        "vertices",
        len(mesh.faces),
        "faces",
        topology["triangles"],
        "triangles",
    )


if __name__ == "__main__":
    run()
