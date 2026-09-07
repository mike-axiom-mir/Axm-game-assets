#!/usr/bin/env python3
from math import cos, pi, sin

from native_animation import AnimationClip, AnimationTrack, contact_drift, pose_skeleton, validate_animation_clip
from native_geometry import Mesh
from native_skin import Joint, Skeleton, SkinWeights, skin_vertices


def run() -> None:
    mesh = Mesh("contact_fixture", [(0.0, 0.0, 0.0), (0.0, 2.0, 0.0), (0.2, 2.0, 0.0)], [(0, 1, 2)])
    skeleton = Skeleton([Joint("root"), Joint("hand", parent=0, translation=(0.0, 1.0, 0.0))])
    weights = SkinWeights(
        joints=[(0, 0, 0, 0), (1, 0, 0, 0), (1, 0, 0, 0)],
        weights=[(1.0, 0.0, 0.0, 0.0), (1.0, 0.0, 0.0, 0.0), (1.0, 0.0, 0.0, 0.0)],
    )
    half = pi * 0.5
    clip = AnimationClip("hand_swing", [
        AnimationTrack(
            joint=1,
            path="rotation",
            times=[0.0, 1.0],
            values=[(0.0, 0.0, 0.0, 1.0), (0.0, 0.0, sin(half / 2.0), cos(half / 2.0))],
        )
    ])
    report = validate_animation_clip(clip, skeleton)
    assert report["status"] == "pass" and report["duration"] == 1.0
    posed = pose_skeleton(skeleton, clip, 1.0)
    vertices = skin_vertices(mesh, weights, skeleton, posed)
    assert vertices[1][0] < -0.99 and abs(vertices[1][1] - 1.0) < 1e-8

    root_contact = contact_drift(mesh, weights, skeleton, clip, [0], [0.0, 0.25, 0.5, 0.75, 1.0])
    hand_contact = contact_drift(mesh, weights, skeleton, clip, [1, 2], [0.0, 0.25, 0.5, 0.75, 1.0])
    assert root_contact["max_drift"] < 1e-9
    assert hand_contact["max_drift"] > 1.0

    duplicate = AnimationClip("bad", [
        AnimationTrack(1, "rotation", [0.0], [(0.0, 0.0, 0.0, 1.0)]),
        AnimationTrack(1, "rotation", [0.0], [(0.0, 0.0, 0.0, 1.0)]),
    ])
    assert validate_animation_clip(duplicate, skeleton)["status"] == "fail"
    print("NATIVE ANIMATION TEST PASS", root_contact["max_drift"], hand_contact["max_drift"])


if __name__ == "__main__":
    run()
