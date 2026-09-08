#!/usr/bin/env python3
from native_geometry import make_box, triangulate
from native_surface_uv import subdivide_with_uv
from native_uv import box_project, read_obj_uv, validate_uv


def run() -> None:
    box = make_box((1.0, 1.0, 1.0), name="uv_subdiv_box")
    box_uv = box_project(box)
    box_sub, box_sub_uv = subdivide_with_uv(box, box_uv, levels=1)
    assert len(triangulate(box_sub).faces) == len(triangulate(box).faces) * 4
    assert validate_uv(box_sub, box_sub_uv)["status"] == "pass"
    assert box_sub.vertices[:len(box.vertices)] == box.vertices
    assert box_sub_uv.uvs[:len(box_uv.uvs)] == box_uv.uvs
    assert len(box_sub_uv.uvs) > len(box_sub.vertices), "explicit UV seams should remain separate from shared geometry"

    head, head_uv = read_obj_uv("seed_data/hm08_head_v0.2/head.obj", name="hm08_head_v0_2")
    first, first_uv = subdivide_with_uv(head, head_uv, levels=1, name="hm08_head_subdiv1")
    second, second_uv = subdivide_with_uv(head, head_uv, levels=1, name="hm08_head_subdiv1")
    assert first.vertices == second.vertices
    assert first.faces == second.faces
    assert first_uv.uvs == second_uv.uvs
    assert first_uv.face_uvs == second_uv.face_uvs
    assert first.vertices[:len(head.vertices)] == head.vertices
    assert first_uv.uvs[:len(head_uv.uvs)] == head_uv.uvs
    assert len(first.faces) == 8336 * 4
    assert len(first.vertices) > len(head.vertices)
    assert validate_uv(first, first_uv)["status"] == "pass"

    print(
        "NATIVE SURFACE UV TEST PASS",
        {"box_vertices":len(box_sub.vertices),"box_uvs":len(box_sub_uv.uvs),"box_triangles":len(box_sub.faces)},
        {"head_vertices":len(head.vertices),"subdiv_vertices":len(first.vertices),"head_uvs":len(head_uv.uvs),"subdiv_uvs":len(first_uv.uvs),"subdiv_triangles":len(first.faces)},
    )


if __name__ == "__main__":
    run()
