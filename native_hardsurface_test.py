#!/usr/bin/env python3
from native_hardsurface import sentinel_armor_plate, validate_detail_progression


def run() -> None:
    report = validate_detail_progression()
    assert report["status"] == "pass", report
    triangles = [entry["triangles"] for entry in report["levels"]]
    components = [entry["components"] for entry in report["levels"]]
    assert triangles[0] < triangles[1] < triangles[2] < triangles[3]
    assert components == sorted(components) and len(set(components)) == 4
    mesh, high = sentinel_armor_plate(3)
    assert "biomech_ports" in high.semantic_features and "vent_array" in high.semantic_features
    print("NATIVE HARDSURFACE TEST PASS", triangles, components, high.semantic_features)


if __name__ == "__main__":
    run()
