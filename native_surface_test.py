#!/usr/bin/env python3
from native_geometry import make_uv_sphere, topology_report, triangulate
from native_surface import deform, displacement_stats, gaussian_mask, normal_displace, smooth, subdivide, validate_multires


def run() -> None:
    base = make_uv_sphere(1.0, segments=12, rings=6, name="organic_fixture")
    base_triangles = len(triangulate(base).faces)
    assert base_triangles == 120
    level1 = subdivide(base, 1, name="organic_l1")
    level2 = subdivide(base, 2, name="organic_l2")
    assert len(level1.faces) == 480
    assert len(level2.faces) == 1920
    assert topology_report(level2)["closed_two_manifold_candidate"] is True

    smoothed = smooth(level2, iterations=2, strength=0.15)
    assert len(smoothed.vertices) == len(level2.vertices)
    assert len(smoothed.faces) == len(level2.faces)

    mask = gaussian_mask((0.0, 0.65, 0.75), 0.35)
    pushed = deform(smoothed, (0.0, 0.0, 0.08), mask=mask)
    region_stats = displacement_stats(smoothed, pushed)
    assert region_stats["max"] > 0.05
    assert region_stats["mean"] < region_stats["max"]

    displaced_a = normal_displace(pushed, 0.006, seed=77, mask=mask)
    displaced_b = normal_displace(pushed, 0.006, seed=77, mask=mask)
    displaced_c = normal_displace(pushed, 0.006, seed=78, mask=mask)
    assert displaced_a.vertices == displaced_b.vertices
    assert displaced_a.vertices != displaced_c.vertices
    micro = displacement_stats(pushed, displaced_a)
    assert micro["max"] <= 0.0060001

    report = validate_multires(base, displaced_a)
    assert report["status"] == "pass", report
    assert report["source_triangles"] == 120
    assert report["result_triangles"] == 1920
    print("NATIVE SURFACE TEST PASS", report["source_triangles"], "->", report["result_triangles"], region_stats, micro)


if __name__ == "__main__":
    run()
