#!/usr/bin/env python3
from math import pi, sin, cos

from native_attribute_lod import as_character_inputs, deformation_error, from_mesh, simplify, validate
from native_geometry import Mesh
from native_morph import MorphTarget
from native_skin import Joint, Skeleton, SkinWeights
from native_uv import UVMap, validate_uv


def grid(width=12, height=8):
    vertices = []
    uvs = []
    faces = []
    face_uvs = []
    for y in range(height + 1):
        for x in range(width + 1):
            vertices.append((x / width - 0.5, y / height * 2.0, 0.0))
            uvs.append((x / width, y / height))

    def idx(x, y):
        return y * (width + 1) + x

    for y in range(height):
        for x in range(width):
            a, b, c, d = idx(x, y), idx(x + 1, y), idx(x + 1, y + 1), idx(x, y + 1)
            faces.append((a, b, c, d))
            face_uvs.append((a, b, c, d))
    mesh = Mesh("skinned_grid", vertices, faces)
    uv = UVMap(uvs, face_uvs, "grid")
    joints = []
    weights = []
    morph = []
    for px, py, _ in vertices:
        t = max(0.0, min(1.0, (py - 0.6) / 0.8))
        joints.append((0, 1, 0, 0))
        weights.append((1.0 - t, t, 0.0, 0.0))
        morph.append((0.0, 0.0, 0.06 * (1.0 - abs(px) * 2.0) * t))
    skin = SkinWeights(joints, weights)
    target = MorphTarget("muscle_bulge", morph)
    return mesh, uv, skin, [target]


def run():
    mesh, uv, skin, morphs = grid()
    source = from_mesh(mesh, uv, skin=skin, morph_targets=morphs)
    lod = simplify(source, spatial_resolution=6, uv_resolution=6, normal_resolution=2)
    assert len(lod.vertices) < len(source.vertices), (len(source.vertices), len(lod.vertices))
    assert len(lod.triangles) < len(source.triangles), (len(source.triangles), len(lod.triangles))
    assert validate(lod, joint_count=2)["status"] == "pass"
    assert all(len(vertex.morph_deltas) == 1 for vertex in lod.vertices)

    lod_mesh, lod_uv, lod_skin, lod_morphs = as_character_inputs(lod)
    assert validate_uv(lod_mesh, lod_uv)["status"] == "pass"
    assert len(lod_skin.weights) == len(lod.vertices)
    assert len(lod_morphs) == 1 and len(lod_morphs[0].position_deltas) == len(lod.vertices)

    bind = Skeleton([Joint("root"), Joint("upper", parent=0, translation=(0.0, 1.0, 0.0))])
    angle = pi * 0.35
    posed = Skeleton([
        Joint("root"),
        Joint("upper", parent=0, translation=(0.0, 1.0, 0.0), rotation=(0.0, 0.0, sin(angle / 2), cos(angle / 2))),
    ])
    error = deformation_error(source, lod, bind, posed)
    assert error["max"] < 0.08, error
    print(
        "NATIVE ATTRIBUTE LOD TEST PASS",
        len(source.vertices), "->", len(lod.vertices), "verts",
        len(source.triangles), "->", len(lod.triangles), "tris",
        error,
    )


if __name__ == "__main__":
    run()
