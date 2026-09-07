#!/usr/bin/env python3
from pathlib import Path
from tempfile import TemporaryDirectory

from native_geometry import (
    aabb_collision,
    bounds,
    center_at_origin,
    lod_chain,
    make_box,
    make_uv_sphere,
    read_obj,
    scale,
    topology_report,
    translate,
    triangulate,
    vertex_normals,
    write_obj,
)


def run() -> None:
    box = make_box((2.0, 4.0, 6.0))
    assert bounds(box) == ((-1.0, -2.0, -3.0), (1.0, 2.0, 3.0))
    moved = translate(box, (3.0, 2.0, 1.0))
    centered = center_at_origin(moved)
    assert bounds(centered) == bounds(box)
    scaled = scale(box, 0.5)
    assert bounds(scaled) == ((-0.5, -1.0, -1.5), (0.5, 1.0, 1.5))

    tri_box = triangulate(box)
    report = topology_report(tri_box)
    assert report["triangles"] == 12
    assert report["closed_two_manifold_candidate"] is True
    assert len(vertex_normals(tri_box)) == len(tri_box.vertices)
    assert aabb_collision(tri_box)["type"] == "aabb"

    sphere = make_uv_sphere(1.0, segments=32, rings=16)
    chain = lod_chain(sphere)
    faces = [len(level.faces) for level in chain]
    assert len(chain) == 4
    assert all(a > b for a, b in zip(faces, faces[1:])), faces
    assert topology_report(chain[0])["closed_two_manifold_candidate"] is True

    with TemporaryDirectory() as tmp:
        path = Path(tmp) / "sphere.obj"
        write_obj(chain[1], path)
        restored = read_obj(path)
        assert len(restored.vertices) == len(chain[1].vertices)
        assert len(restored.faces) == len(chain[1].faces)
        assert topology_report(restored)["invalid_indices"] == 0

    print("NATIVE GEOMETRY TEST PASS", faces)


if __name__ == "__main__":
    run()
