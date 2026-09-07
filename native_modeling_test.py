#!/usr/bin/env python3
from native_geometry import topology_report, triangulate
from native_modeling import chamfered_rectangle, extrude_polygon, make_chamfered_box, make_cylinder


def run() -> None:
    profile = chamfered_rectangle(2.0, 1.0, 0.15)
    assert len(profile) == 8
    plate = make_chamfered_box(2.0, 1.0, 0.2, 0.15)
    cylinder = make_cylinder(0.25, 0.4, segments=12)
    assert topology_report(plate)["closed_two_manifold_candidate"] is True
    assert topology_report(cylinder)["closed_two_manifold_candidate"] is True
    assert len(triangulate(plate).faces) == 28
    assert len(triangulate(cylinder).faces) == 44
    custom = extrude_polygon([(-1.0,-0.5),(1.0,-0.5),(0.5,0.5),(-0.5,0.5)], 0.3)
    assert topology_report(custom)["closed_two_manifold_candidate"] is True
    print("NATIVE MODELING TEST PASS", len(triangulate(plate).faces), len(triangulate(cylinder).faces))


if __name__ == "__main__":
    run()
