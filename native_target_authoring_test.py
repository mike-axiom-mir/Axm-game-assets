#!/usr/bin/env python3
from native_geometry import make_uv_sphere, scale
from native_target_authoring import author_normal_target, author_offset_target, box_region, gaussian_region
from native_targets import apply_target, validate_target


def run() -> None:
    head = scale(make_uv_sphere(1.0, segments=20, rings=10, name="head_seed"), (0.16, 0.22, 0.18))
    front_nose = gaussian_region((0.0, 0.0, 0.17), (0.055, 0.07, 0.06))
    nose = author_normal_target(head, "nose_bridge_forward", 0.025, region=front_nose, threshold=1e-5)
    assert validate_target(nose, vertex_count=len(head.vertices))["status"] == "pass"
    assert 0 < len(nose.deltas) < len(head.vertices)
    nose_mesh = apply_target(head, nose, 1.0)
    assert nose_mesh.faces == head.faces
    assert nose_mesh.vertices != head.vertices

    left_cheek = box_region((-0.14, -0.03, 0.08), (-0.02, 0.08, 0.19), feather=0.03)
    injury = author_offset_target(head, "injured_left_cheek", (0.008, -0.004, 0.006), region=left_cheek, threshold=1e-5)
    assert validate_target(injury, vertex_count=len(head.vertices))["status"] == "pass"
    assert 0 < len(injury.deltas) < len(head.vertices)

    unchanged = [index for index in range(len(head.vertices)) if index not in injury.deltas]
    assert unchanged
    injured_mesh = apply_target(head, injury, 1.0)
    assert all(injured_mesh.vertices[index] == head.vertices[index] for index in unchanged)
    print("NATIVE TARGET AUTHORING TEST PASS", len(nose.deltas), "nose rows", len(injury.deltas), "injury rows")


if __name__ == "__main__":
    run()
