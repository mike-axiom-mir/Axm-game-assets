#!/usr/bin/env python3
from native_catmull_clark import catmull_clark_with_uv
from native_geometry import make_box, topology_report, triangulate
from native_uv import box_project, read_obj_uv, validate_uv


def run() -> None:
    box = make_box((1.0,1.0,1.0), name="cc_box")
    box_uv = box_project(box)
    box_cc, box_cc_uv = catmull_clark_with_uv(box, box_uv, levels=1, shape_strength=0.5)
    assert len(box_cc.faces) == 24
    assert len(triangulate(box_cc).faces) == 48
    assert validate_uv(box_cc, box_cc_uv)["status"] == "pass"
    assert len(box_cc_uv.uvs) > len(box_cc.vertices), "face-varying seams should remain explicit"

    head, head_uv = read_obj_uv("seed_data/hm08_head_v0.2/head.obj", name="hm08_head_v0_2")
    first, first_uv = catmull_clark_with_uv(head, head_uv, levels=1, shape_strength=0.45, name="hm08_head_cc")
    second, second_uv = catmull_clark_with_uv(head, head_uv, levels=1, shape_strength=0.45, name="hm08_head_cc")
    assert first.vertices == second.vertices
    assert first.faces == second.faces
    assert first_uv.uvs == second_uv.uvs
    assert first_uv.face_uvs == second_uv.face_uvs
    assert len(first.faces) == sum(len(face) for face in head.faces)
    assert len(triangulate(first).faces) == 8336 * 4
    assert validate_uv(first, first_uv)["status"] == "pass"
    topology = topology_report(first)
    assert topology["invalid_indices"] == 0
    assert topology["degenerate_faces"] == 0
    assert topology["nonmanifold_edges"] == 0

    original_count = len(head.vertices)
    distances = [
        sum((first.vertices[index][axis]-head.vertices[index][axis])**2 for axis in range(3))**0.5
        for index in range(original_count)
    ]
    assert max(distances) > 0.0
    assert max(distances) < 0.05, max(distances)  # <5mm in raw dm units converted by x100.

    print(
        "CATMULL CLARK TEST PASS",
        {"box_vertices":len(box_cc.vertices),"box_uvs":len(box_cc_uv.uvs),"box_faces":len(box_cc.faces)},
        {"head_vertices":len(first.vertices),"head_uvs":len(first_uv.uvs),"head_quads":len(first.faces),"head_triangles":len(triangulate(first).faces),"max_original_mm":max(distances)*100.0},
    )


if __name__ == "__main__":
    run()
