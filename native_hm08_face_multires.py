#!/usr/bin/env python3
"""Parallel hm08 face+eyes multires LOD0 candidate.

The control is the preferred physical-scale skin + source-grounded eyes package.
This candidate changes only head geometry: one UV-preserving subdivision level
plus a light boundary-preserving smoothing pass. Skin/eye texture bytes are
reused unchanged so Godot A/B evidence can judge geometry rather than material.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from native_geometry import scale, topology_report
from native_hm08_face_eyes import RAW_TO_M, SEED_ROOT, _combine_with_uv, _translated_eye_layers, build_face_eyes_package
from native_hm08_face_proof import DEFAULT_WEIGHTS
from native_multi_gltf import MaterialPrimitive, write_multi_gltf
from native_surface import boundary_vertices, smooth
from native_surface_uv import subdivide_with_uv
from native_targets import load_target, mix_targets
from native_uv import read_obj_uv, validate_uv

SCHEMA = "axm.game-assets.hm08-face-multires.v0.1"
ASSET_NAME = "sentinel_hm08_face_eyes_multires_v0_1"


def _sha(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _original_vertex_displacement(before, after, original_count: int) -> dict[str, float | int]:
    distances = []
    for index in range(original_count):
        a = before.vertices[index]
        b = after.vertices[index]
        distance = sum((b[axis] - a[axis]) ** 2 for axis in range(3)) ** 0.5
        distances.append(distance)
    moved = [distance for distance in distances if distance > 1e-12]
    return {
        "original_vertices": original_count,
        "moved_original_vertices": len(moved),
        "mean_raw": sum(moved) / len(moved) if moved else 0.0,
        "max_raw": max(distances, default=0.0),
        "mean_mm": (sum(moved) / len(moved) if moved else 0.0) * 100.0,
        "max_mm": max(distances, default=0.0) * 100.0,
    }


def build_face_multires_package(
    output: str | Path,
    *,
    texture_size: int = 128,
    skin_seed: int = 20801,
    eye_seed: int = 31991,
    smoothing_strength: float = 0.10,
) -> dict[str, object]:
    root = Path(output)
    root.mkdir(parents=True, exist_ok=True)

    # Build the preferred current control first. Its skin/eye files are reused
    # byte-for-byte by the multires candidate.
    control = build_face_eyes_package(
        root,
        texture_size=texture_size,
        skin_seed=skin_seed,
        eye_seed=eye_seed,
        skin_mode="physical_v0.1",
    )
    shared_skin_hashes = {
        name: control["skin"]["maps"][name]["sha256"]
        for name in ("base_color", "normal", "orm")
    }

    raw_head, head_uv = read_obj_uv(SEED_ROOT / "head.obj", name="hm08_head_v0_2")
    library = {
        name: load_target(SEED_ROOT / "targets" / f"{name}.target", license="CC0-source-remap")
        for name in sorted(DEFAULT_WEIGHTS)
    }
    identity, identity_state = mix_targets(raw_head, library, DEFAULT_WEIGHTS, name="sentinel_identity_multires_source")
    original_count = len(identity.vertices)
    source_boundary = boundary_vertices(identity)
    subdivided, subdiv_uv = subdivide_with_uv(identity, head_uv, levels=1, name="sentinel_face_multires_subdiv1")
    if subdivided.vertices[:original_count] != identity.vertices:
        raise ValueError("UV-preserving subdivision failed to retain original vertex positions before smoothing")
    smoothed = smooth(
        subdivided,
        iterations=1,
        strength=smoothing_strength,
        preserve_boundary=True,
        name="sentinel_face_multires_smoothed",
    )
    uv_report = validate_uv(smoothed, subdiv_uv)
    if uv_report["status"] != "pass":
        raise ValueError(f"multires smoothing broke UV state: {uv_report}")
    displacement = _original_vertex_displacement(identity, smoothed, original_count)
    source_boundary_unchanged = all(smoothed.vertices[index] == identity.vertices[index] for index in source_boundary)
    topology = topology_report(smoothed)
    head_m = scale(smoothed, RAW_TO_M, name="sentinel_face_multires_meters")

    eye_metadata = json.loads((SEED_ROOT / "eye-landmarks.json").read_text(encoding="utf-8"))
    radius_m = float(eye_metadata["prototype_eye_radius_m"])
    left_center = tuple(float(value) for value in eye_metadata["eyes"]["left"]["center_m"])
    right_center = tuple(float(value) for value in eye_metadata["eyes"]["right"]["center_m"])
    left_layers, left_uvs, left_report = _translated_eye_layers(left_center, radius_m, side="left")
    right_layers, right_uvs, right_report = _translated_eye_layers(right_center, radius_m, side="right")
    layer_meshes = {
        layer: _combine_with_uv(
            [(left_layers[layer], left_uvs[layer]), (right_layers[layer], right_uvs[layer])],
            name=f"sentinel_{layer}_pair_multires_control",
        )
        for layer in ("sclera", "iris", "pupil", "cornea")
    }

    primitives = [
        MaterialPrimitive(
            head_m,
            subdiv_uv,
            "AXM_Sentinel_Skin_Physical_v0_1",
            "textures/skin/base_color.png",
            "textures/skin/normal.png",
            "textures/skin/orm.png",
            metallic_factor=0.0,
        ),
        MaterialPrimitive(
            layer_meshes["sclera"][0], layer_meshes["sclera"][1],
            "AXM_Eye_Sclera",
            "textures/eyes/sclera_base_color.png",
            "textures/eyes/sclera_normal.png",
            "textures/eyes/sclera_orm.png",
            metallic_factor=0.0,
        ),
        MaterialPrimitive(
            layer_meshes["iris"][0], layer_meshes["iris"][1],
            "AXM_Eye_Iris",
            "textures/eyes/iris_base_color.png",
            "textures/eyes/iris_normal.png",
            "textures/eyes/iris_orm.png",
            metallic_factor=0.0,
        ),
        MaterialPrimitive(
            layer_meshes["pupil"][0], layer_meshes["pupil"][1],
            "AXM_Eye_Pupil",
            "textures/eyes/pupil_base_color.png",
            "textures/eyes/pupil_normal.png",
            "textures/eyes/pupil_orm.png",
            metallic_factor=0.0,
            roughness_factor=0.24,
        ),
        MaterialPrimitive(
            layer_meshes["cornea"][0], layer_meshes["cornea"][1],
            "AXM_Eye_Cornea_Prototype",
            "textures/eyes/cornea_base_color.png",
            "textures/eyes/cornea_normal.png",
            "textures/eyes/cornea_orm.png",
            metallic_factor=0.0,
            roughness_factor=0.015,
            base_color_factor=(1.0, 1.0, 1.0, 0.12),
            alpha_mode="BLEND",
        ),
    ]
    delivery = write_multi_gltf(primitives, root, name=ASSET_NAME)

    acceptance = {
        "preferred_physical_skin_control_green": all(control["acceptance"].values()) and control["skin_mode"] == "physical_v0.1",
        "identity_target_mix_present": len(identity_state["applied"]) == len(DEFAULT_WEIGHTS),
        "one_subdivision_level": len(subdivided.faces) == 8336 * 4,
        "multires_vertex_growth": len(subdivided.vertices) > original_count,
        "uv_preserved": uv_report["status"] == "pass",
        "source_boundaries_unchanged": source_boundary_unchanged,
        "structural_topology_valid": topology["invalid_indices"] == 0 and topology["degenerate_faces"] == 0 and topology["nonmanifold_edges"] == 0,
        "smoothing_displacement_bounded": 0.0 < displacement["max_mm"] < 3.0,
        "same_skin_texture_hashes": shared_skin_hashes == {name:control["skin"]["maps"][name]["sha256"] for name in shared_skin_hashes},
        "both_eye_geometries_valid": left_report["status"] == "pass" and right_report["status"] == "pass",
        "five_semantic_primitives": delivery["primitive_count"] == 5,
        "gltf_structural_valid": delivery["validation"]["status"] == "pass",
    }
    manifest: dict[str, object] = {
        "schema": SCHEMA,
        "asset": ASSET_NAME,
        "ab_control": {
            "asset": control["asset"],
            "gltf_sha256": control["delivery"]["gltf_sha256"],
            "skin_mode": control["skin_mode"],
            "shared_skin_map_hashes": shared_skin_hashes,
        },
        "ab_variable": "uv_preserving_subdivision_plus_light_smoothing_only",
        "subdivision": {
            "levels": 1,
            "source_vertices": original_count,
            "result_vertices": len(smoothed.vertices),
            "source_triangles": 8336,
            "result_triangles": len(smoothed.faces),
            "smoothing_iterations": 1,
            "smoothing_strength": smoothing_strength,
            "source_boundary_vertices": len(source_boundary),
            "source_boundary_unchanged": source_boundary_unchanged,
            "original_vertex_displacement": displacement,
        },
        "uv": uv_report,
        "topology": topology,
        "delivery": delivery,
        "acceptance": acceptance,
        "truth": {
            "high_end_anatomy_claim": False,
            "preferred_lod0_claim": False,
            "notes": [
                "This candidate changes head geometry only; physical skin and eye texture bytes are shared with the control.",
                "Subdivision/smoothing is derived delivery state. Canonical hm08 identity targets remain untouched and reconstructable.",
                "Promotion requires real Godot close-view evidence, especially profile silhouette and eyelid/ear retention."
            ]
        },
    }
    payload = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8")
    (root / "face-multires-package.json").write_bytes(payload)
    manifest["manifest_sha256"] = _sha(payload)
    if not all(acceptance.values()):
        raise ValueError(f"multires face package acceptance failed: {acceptance}")
    return manifest


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("output", nargs="?", default="build/hm08-face-multires")
    parser.add_argument("--texture-size", type=int, default=128)
    parser.add_argument("--smoothing-strength", type=float, default=0.10)
    args = parser.parse_args()
    result = build_face_multires_package(args.output, texture_size=args.texture_size, smoothing_strength=args.smoothing_strength)
    print(json.dumps({"acceptance":result["acceptance"],"subdivision":result["subdivision"],"delivery":result["delivery"]}, indent=2))
