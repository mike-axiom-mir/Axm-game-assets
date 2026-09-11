#!/usr/bin/env python3
from tempfile import TemporaryDirectory

from native_sentinel_armor import (
    MIN_BODY_CLEARANCE_M,
    UNDERSUIT_OFFSET_M,
    build_sentinel_armor,
    write_sentinel_armor_package,
)


def _component_map(components):
    return {component.name: component for component in components}


def _bounds(mesh):
    xs = [v[0] for v in mesh.vertices]
    ys = [v[1] for v in mesh.vertices]
    zs = [v[2] for v in mesh.vertices]
    return (min(xs), min(ys), min(zs)), (max(xs), max(ys), max(zs))


def _mirror_pair(left, right, tolerance=0.035):
    llo, lhi = _bounds(left.mesh)
    rlo, rhi = _bounds(right.mesh)
    left_center_x = (llo[0] + lhi[0]) * 0.5
    right_center_x = (rlo[0] + rhi[0]) * 0.5
    left_center_y = (llo[1] + lhi[1]) * 0.5
    right_center_y = (rlo[1] + rhi[1]) * 0.5
    left_center_z = (llo[2] + lhi[2]) * 0.5
    right_center_z = (rlo[2] + rhi[2]) * 0.5
    assert abs(left_center_x + right_center_x) <= tolerance, (left.name, right.name, left_center_x, right_center_x)
    assert abs(left_center_y - right_center_y) <= tolerance, (left.name, right.name, left_center_y, right_center_y)
    assert abs(left_center_z - right_center_z) <= tolerance, (left.name, right.name, left_center_z, right_center_z)


def run() -> None:
    first_components, first = build_sentinel_armor()
    second_components, second = build_sentinel_armor()
    assert first == second
    assert len(first_components) == len(second_components)
    for a, b in zip(first_components, second_components):
        assert a.name == b.name
        assert a.role == b.role
        assert a.material_group == b.material_group
        assert a.mesh.vertices == b.mesh.vertices
        assert a.mesh.faces == b.mesh.faces

    assert first["schema"] == "axm.game-assets.sentinel-armor.v0.1"
    assert first["status"] == "pass", first
    assert first["source_body"]["vertices"] == 13380
    assert first["source_body"]["faces"] == 13378
    assert first["component_count"] >= 14
    assert first["primary_component_count"] >= 10
    assert first["mechanical_component_count"] >= 4
    assert abs(first["undersuit_offset_m"] - UNDERSUIT_OFFSET_M) < 1e-12
    assert first["minimum_body_clearance_m"] == MIN_BODY_CLEARANCE_M
    assert first["minimum_clearance_over_undersuit_m"] >= 0.004
    assert all(float(row["measured_body_clearance_m"]) >= MIN_BODY_CLEARANCE_M for row in first["fit"].values())
    assert first["truth"]["source_fitted"] is True
    assert first["truth"]["production_armor_claim"] is False

    components = _component_map(first_components)
    for left_name, right_name in (
        ("left_shoulder", "right_shoulder"),
        ("left_forearm", "right_forearm"),
        ("left_thigh", "right_thigh"),
        ("left_shin", "right_shin"),
        ("left_chest_port", "right_chest_port"),
    ):
        _mirror_pair(components[left_name], components[right_name])
        assert components[left_name].paired_with == right_name
        assert components[right_name].paired_with == left_name

    with TemporaryDirectory() as first_dir, TemporaryDirectory() as second_dir:
        a = write_sentinel_armor_package(first_dir, texture_size=64)
        b = write_sentinel_armor_package(second_dir, texture_size=64)
        assert a["acceptance"] == b["acceptance"]
        assert all(a["acceptance"].values()), a["acceptance"]
        assert a["delivery"]["gltf_sha256"] == b["delivery"]["gltf_sha256"]
        assert a["delivery"]["binary_sha256"] == b["delivery"]["binary_sha256"]
        assert a["delivery"]["primitive_count"] == first["component_count"]
        assert a["delivery"]["material_count"] == first["component_count"]
        assert a["materials"]["primary"]["maps"]["base_color"]["sha256"] == b["materials"]["primary"]["maps"]["base_color"]["sha256"]
        assert a["materials"]["mechanical"]["maps"]["base_color"]["sha256"] == b["materials"]["mechanical"]["maps"]["base_color"]["sha256"]
        assert a["truth"]["visual_promotion"] is False

    print("SENTINEL ARMOR TEST PASS", {
        "components": first["component_count"],
        "primary": first["primary_component_count"],
        "mechanical": first["mechanical_component_count"],
        "triangles": first["triangles"],
        "min_clearance_mm": min(float(row["measured_body_clearance_m"]) for row in first["fit"].values()) * 1000.0,
    })


if __name__ == "__main__":
    run()
