#!/usr/bin/env python3
from math import pi, sin, cos
from pathlib import Path
from tempfile import TemporaryDirectory

from native_animation import AnimationClip, AnimationTrack
from native_character_lod_proof import prove_character_lods
from native_geometry import Mesh
from native_morph import MorphTarget
from native_skin import Joint, Skeleton, SkinWeights
from native_uv import UVMap


def fixture(width=12, height=8):
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
    mesh = Mesh("character_lod_fixture", vertices, faces)
    uv = UVMap(uvs, face_uvs, "fixture_grid")
    joints = []
    weights = []
    morph = []
    for x, y, _ in vertices:
        t = max(0.0, min(1.0, (y - 0.6) / 0.8))
        joints.append((0, 1, 0, 0))
        weights.append((1.0 - t, t, 0.0, 0.0))
        morph.append((0.0, 0.0, 0.04 * (1.0 - abs(x) * 2.0) * t))
    skin = SkinWeights(joints, weights)
    morphs = [MorphTarget("bulge", morph)]
    bind = Skeleton([Joint("root"), Joint("upper", parent=0, translation=(0.0, 1.0, 0.0))])
    poses = []
    for angle in (pi * 0.15, pi * 0.35, pi * 0.5):
        poses.append(Skeleton([
            Joint("root"),
            Joint("upper", parent=0, translation=(0.0, 1.0, 0.0), rotation=(0.0, 0.0, sin(angle / 2), cos(angle / 2))),
        ]))
    clip = AnimationClip("bend", [AnimationTrack(1, "rotation", [0.0, 1.0], [(0, 0, 0, 1), (0, 0, sin(pi * 0.25), cos(pi * 0.25))])])
    return mesh, uv, skin, morphs, bind, poses, [clip]


def run():
    mesh, uv, skin, morphs, bind, poses, animations = fixture()
    with TemporaryDirectory() as tmp:
        proof = prove_character_lods(
            mesh,
            uv,
            skin,
            morphs,
            bind,
            poses,
            Path(tmp),
            resolutions=((10, 8), (6, 6), (4, 4)),
            max_deformation_error=0.03,
            animations=animations,
            texture_size=16,
        )
        assert all(proof["acceptance"].values()), proof
        triangles = [level["triangles"] for level in proof["levels"]]
        assert triangles[0] > triangles[1] > triangles[2]
        assert proof["levels"][-1]["deformation"]["max"] < 0.03
        assert proof["levels"][-1]["delivery"]["morph_targets"] == 1
        assert proof["levels"][-1]["delivery"]["animations"] == 1
        print(
            "NATIVE CHARACTER LOD PROOF PASS",
            proof["source"]["triangles"], "->", triangles,
            "max error", proof["levels"][-1]["deformation"]["max"],
        )


if __name__ == "__main__":
    run()
