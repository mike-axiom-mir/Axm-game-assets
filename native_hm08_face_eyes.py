#!/usr/bin/env python3
"""Layer repaired hm08 human face with source-grounded AXM eyes.

Canonical hm08 seed/targets remain in MakeHuman decimeters. This delivery
explicitly converts the human face to meters, places two layered Forge eyes at
pinned helper-eye centers, and emits five semantic glTF material primitives:
skin, sclera, iris, pupil and prototype cornea.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from native_eye import make_eye, validate_eye
from native_eye_material import IrisSpec, iris_fields, sclera_fields
from native_geometry import Mesh, combine, scale, translate
from native_hm08_face_proof import DEFAULT_WEIGHTS
from native_multi_gltf import MaterialPrimitive, write_multi_gltf
from native_pbr import png_bytes
from native_skin_material import SkinMaterialSpec, write_skin_material
from native_targets import load_target, mix_targets
from native_uv import UVMap, box_project, read_obj_uv, spherical_project, validate_uv

SCHEMA = "axm.game-assets.hm08-face-eyes.v0.1"
SEED_ROOT = Path("seed_data/hm08_head_v0.2")
RAW_TO_M = 0.1


def _sha(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _write_png(path: Path, size: int, channels: int, pixels: bytes) -> str:
    data = png_bytes(size, size, channels, pixels)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return _sha(data)


def _orm(roughness: bytes, metallic: int = 0) -> bytes:
    out = bytearray()
    for rough in roughness:
        out.extend((255, rough, metallic))
    return bytes(out)


def _flat_rgb(size: int, rgb: tuple[int, int, int]) -> bytes:
    return bytes(rgb) * (size * size)


def _flat_normal(size: int) -> bytes:
    return bytes((128, 128, 255)) * (size * size)


def _flat_orm(size: int, roughness: float) -> bytes:
    rough = max(0, min(255, round(roughness * 255)))
    return bytes((255, rough, 0)) * (size * size)


def _combine_with_uv(items: list[tuple[Mesh, UVMap]], *, name: str) -> tuple[Mesh, UVMap]:
    meshes = [mesh for mesh, _ in items]
    combined = combine(meshes, name=name)
    uvs = []
    face_uvs = []
    uv_offset = 0
    for mesh, uvmap in items:
        report = validate_uv(mesh, uvmap)
        if report["status"] != "pass":
            raise ValueError(f"invalid source UV while combining {mesh.name}: {report}")
        uvs.extend(uvmap.uvs)
        face_uvs.extend(tuple(index + uv_offset for index in face) for face in uvmap.face_uvs)
        uv_offset += len(uvmap.uvs)
    return combined, UVMap(uvs, face_uvs, "combined_eye_layer")


def _translated_eye_layers(center_m: tuple[float, float, float], radius_m: float, *, side: str):
    eye = make_eye(radius_m, name=f"{side}_eye")
    report = validate_eye(eye)
    if report["status"] != "pass":
        raise ValueError(f"{side} eye geometry invalid: {report}")
    translated = {
        layer: translate(mesh, center_m, name=f"{side}_{layer}")
        for layer, mesh in eye.components.items()
    }
    uvs = {
        "sclera": spherical_project(translated["sclera"]),
        "iris": box_project(translated["iris"]),
        "pupil": box_project(translated["pupil"]),
        "cornea": box_project(translated["cornea"]),
    }
    return translated, uvs, report


def build_face_eyes_package(
    output: str | Path,
    *,
    texture_size: int = 128,
    skin_seed: int = 20801,
    eye_seed: int = 31991,
) -> dict[str, object]:
    root = Path(output)
    root.mkdir(parents=True, exist_ok=True)
    seed_manifest = json.loads((SEED_ROOT / "seed-manifest.json").read_text(encoding="utf-8"))
    landmarks = json.loads((SEED_ROOT / "eye-landmarks.json").read_text(encoding="utf-8"))
    if seed_manifest["basemesh_id"] != landmarks["basemesh_id"]:
        raise ValueError("hm08 eye landmarks do not match preferred head seed")

    raw_head, head_uv = read_obj_uv(SEED_ROOT / "head.obj", name="hm08_head_v0_2")
    library = {
        name: load_target(SEED_ROOT / "targets" / f"{name}.target", license="CC0-source-remap")
        for name in sorted(DEFAULT_WEIGHTS)
    }
    raw_variant, target_state = mix_targets(raw_head, library, DEFAULT_WEIGHTS, name="sentinel_face_meters")
    head_m = scale(raw_variant, RAW_TO_M, name="sentinel_face_meters")
    head_uv_report = validate_uv(head_m, head_uv)
    if head_uv_report["status"] != "pass":
        raise ValueError(f"meter conversion broke head UV state: {head_uv_report}")

    radius_m = float(landmarks["prototype_eye_radius_m"])
    left_center = tuple(float(value) for value in landmarks["eyes"]["left"]["center_m"])
    right_center = tuple(float(value) for value in landmarks["eyes"]["right"]["center_m"])
    left_layers, left_uvs, left_report = _translated_eye_layers(left_center, radius_m, side="left")
    right_layers, right_uvs, right_report = _translated_eye_layers(right_center, radius_m, side="right")

    layer_meshes: dict[str, tuple[Mesh, UVMap]] = {}
    for layer in ("sclera", "iris", "pupil", "cornea"):
        layer_meshes[layer] = _combine_with_uv(
            [(left_layers[layer], left_uvs[layer]), (right_layers[layer], right_uvs[layer])],
            name=f"sentinel_{layer}_pair",
        )

    skin_spec = SkinMaterialSpec(
        base_rgb=(166, 119, 101),
        undertone_rgb=(142, 72, 67),
        roughness=0.50,
        oiliness=0.15,
        pore_strength=0.38,
        freckle_density=0.020,
        subsurface_weight_hint=0.56,
        specular_ior_hint=1.40,
    )
    skin = write_skin_material(root / "textures" / "skin", size=texture_size, seed=skin_seed, spec=skin_spec)

    eye_root = root / "textures" / "eyes"
    eye_root.mkdir(parents=True, exist_ok=True)
    iris_spec = IrisSpec(inner_rgb=(86, 104, 71), outer_rgb=(31, 51, 43), filament_rgb=(151, 132, 70), roughness=0.30)
    iris = iris_fields(texture_size, eye_seed, iris_spec)
    sclera = sclera_fields(texture_size, eye_seed + 99)
    texture_receipts = {}
    for name, (channels, pixels) in {**iris, **sclera}.items():
        texture_receipts[name] = _write_png(eye_root / f"{name}.png", texture_size, channels, pixels)
    texture_receipts["iris_orm"] = _write_png(eye_root / "iris_orm.png", texture_size, 3, _orm(iris["iris_roughness"][1]))
    texture_receipts["sclera_orm"] = _write_png(eye_root / "sclera_orm.png", texture_size, 3, _orm(sclera["sclera_roughness"][1]))
    texture_receipts["pupil_base_color"] = _write_png(eye_root / "pupil_base_color.png", texture_size, 3, _flat_rgb(texture_size, (2, 2, 2)))
    texture_receipts["pupil_normal"] = _write_png(eye_root / "pupil_normal.png", texture_size, 3, _flat_normal(texture_size))
    texture_receipts["pupil_orm"] = _write_png(eye_root / "pupil_orm.png", texture_size, 3, _flat_orm(texture_size, 0.24))
    texture_receipts["cornea_base_color"] = _write_png(eye_root / "cornea_base_color.png", texture_size, 3, _flat_rgb(texture_size, (255, 255, 255)))
    texture_receipts["cornea_normal"] = _write_png(eye_root / "cornea_normal.png", texture_size, 3, _flat_normal(texture_size))
    texture_receipts["cornea_orm"] = _write_png(eye_root / "cornea_orm.png", texture_size, 3, _flat_orm(texture_size, 0.015))

    primitives = [
        MaterialPrimitive(
            head_m,
            head_uv,
            "AXM_Sentinel_Skin_Prototype",
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
    delivery = write_multi_gltf(primitives, root, name="sentinel_hm08_face_eyes_v0_1")

    acceptance = {
        "repaired_seed_used": seed_manifest["basemesh_id"] == "axm-hm08-head-v0.2",
        "source_grounded_eye_landmarks": landmarks["truth"]["source_grounded"] is True,
        "explicit_decimeter_to_meter_conversion": RAW_TO_M == 0.1,
        "head_uv_preserved": head_uv_report["status"] == "pass",
        "both_eye_geometries_valid": left_report["status"] == "pass" and right_report["status"] == "pass",
        "five_semantic_primitives": delivery["primitive_count"] == 5,
        "five_semantic_materials": delivery["material_count"] == 5,
        "gltf_structural_valid": delivery["validation"]["status"] == "pass",
        "cornea_alpha_layer_present": "AXM_Eye_Cornea_Prototype" in delivery["material_names"],
    }
    manifest: dict[str, object] = {
        "schema": SCHEMA,
        "asset": "sentinel_hm08_face_eyes_v0_1",
        "seed_basemesh": seed_manifest["basemesh_id"],
        "coordinate_conversion": {"source_unit":"decimeter","delivery_unit":"meter","scale":RAW_TO_M},
        "target_mix": target_state,
        "eye_landmarks": landmarks,
        "eye_geometry": {"left":left_report,"right":right_report},
        "skin": skin,
        "eye_texture_receipts": texture_receipts,
        "delivery": delivery,
        "acceptance": acceptance,
        "truth": {
            "high_end_eye_claim": False,
            "corneal_refraction_claim": False,
            "notes": [
                "Eye centers/radius are source-grounded from pinned hm08 helper-eye geometry rather than fitted by visual guess.",
                "Cornea uses standard alpha blending as a first clear-layer engine test; it does not yet model physical refraction.",
                "Tearline/meniscus, lashes, eyelid wetness and expression-dependent eyelid contact remain later fidelity gates."
            ]
        },
    }
    payload = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8")
    (root / "face-eyes-package.json").write_bytes(payload)
    manifest["manifest_sha256"] = _sha(payload)
    if not all(acceptance.values()):
        raise ValueError(f"face+eyes package acceptance failed: {acceptance}")
    return manifest


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("output", nargs="?", default="build/hm08-face-eyes")
    parser.add_argument("--texture-size", type=int, default=128)
    args = parser.parse_args()
    result = build_face_eyes_package(args.output, texture_size=args.texture_size)
    print(json.dumps({"acceptance":result["acceptance"],"delivery":result["delivery"]}, indent=2))
