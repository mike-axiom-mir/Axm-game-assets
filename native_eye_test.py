#!/usr/bin/env python3
from native_eye import combined_eye, make_eye, validate_eye
from native_geometry import topology_report


def run() -> None:
    eye = make_eye(0.012, name="sentinel_eye")
    report = validate_eye(eye)
    assert report["status"] == "pass", report
    assert set(eye.components) == {"sclera", "iris", "pupil", "cornea"}
    combined = combined_eye(eye)
    assert len(combined.vertices) > len(eye.components["sclera"].vertices)
    assert topology_report(eye.components["cornea"])["closed_two_manifold_candidate"] is True
    assert eye.components["iris"].vertices != eye.components["pupil"].vertices
    print("NATIVE EYE TEST PASS", {name: len(mesh.faces) for name, mesh in eye.components.items()})


if __name__ == "__main__":
    run()
