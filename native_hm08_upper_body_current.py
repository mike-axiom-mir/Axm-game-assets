#!/usr/bin/env python3
"""Current continuous Sentinel human upper-body candidate.

This package moves the already-proven Sentinel face state from the isolated
hm08 head seed onto one continuous pinned hm08 head+neck+torso+arms+hands
surface. The promoted face, eyes, brows, lashes and short-hair stack remain the
visual reference. The body surface is a continuity substrate only: no final
Sentinel musculature, undersuit, armor, rigging, or body-skin-detail claim is
made here.
"""
from __future__ import annotations

import hashlib
import json
from math import sqrt
from pathlib import Path

from native_geometry import scale
from native_hair_material import HairMaterialSpec, write_hair_material
from native_hm08_brow_material import BrowMaterialSpec, write_brow_material
from native_hm08_brows import generate_hm08_brows
from native_hm08_face_eyes import (
    RAW_TO_M,
    _combine_with_uv,
    _translated_eye_layers,
    build_face_eyes_package,
)
from native_hm08_face_proof import DEFAULT_WEIGHTS
from native_hm08_landmarks import derive_hm08_face_landmarks, landmark_packet
from native_hm08_lash_material import LashMaterialSpec, write_lash_material
from native_hm08_lashes import generate_hm08_upper_lashes
from native_hm08_scalp_hair import generate_hm08_short_scalp_hair
from native_hm08_scalp_underlay import build_hm08_scalp_underlay, write_scalp_underlay_material
from native_multi_gltf import MaterialPrimitive, write_multi_gltf
from native_pbr import png_bytes
from native_targets import load_target, mix_targets
from native_uv import read_obj_uv, validate_uv

HEAD_SEED = Path("seed_data/hm08_head_v0.2")
UPPER_SEED = Path("seed_data/hm08_upper_body_v0.1")
SCHEMA = "axm.game-assets.hm08-upper-body-current.v0.1"
ASSET_NAME = "sentinel_hm08_upper_body_current_v0_1"


def _sha(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _write_flat_normal(path: Path, size: int) -> str:
    data = png_bytes(size, size, 3, bytes((128, 128, 255)) * (size * size))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return _sha(data)


def _library(seed_root: Path):
    return {
        name: load_target(seed_root / "targets" / f"{name}.target", license="CC0-source-remap")
        for name in sorted(DEFAULT_WEIGHTS)
    }


def _source_position_overlap(
    head_vertices,
    upper_vertices,
    head_map: dict[str, object],
    upper_map: dict[str, object],
) -> dict[str, object]:
    head_source_to_compact = {int(source): int(compact) for source, compact in head_map["source_to_compact"].items()}
    upper_source_to_compact = {int(source): int(compact) for source, compact in upper_map["source_to_compact"].items()}
    missing = sorted(set(head_source_to_compact) - set(upper_source_to_compact))
    if missing:
        return {"status": "fail", "missing_source_vertices": missing, "compared_vertices": 0, "max_error_raw": None}
    max_error = 0.0
    error_sum = 0.0
    for source, head_index in head_source_to_compact.items():
        upper_index = upper_source_to_compact[source]
        a = head_vertices[head_index]
        b = upper_vertices[upper_index]
        dx, dy, dz = a[0] - b[0], a[1] - b[1], a[2] - b[2]
        error = sqrt(dx * dx + dy * dy + dz * dz)
        max_error = max(max_error, error)
        error_sum += error
    count = len(head_source_to_compact)
    return {
        "status": "pass" if max_error <= 1e-12 else "fail",
        "missing_source_vertices": [],
        "compared_vertices": count,
        "max_error_raw": max_error,
        "mean_error_raw": error_sum / float(max(count, 1)),
        "max_error_m": max_error * RAW_TO_M,
    }


def build_current_upper_body_package(
    output: str | Path,
    *,
    texture_size: int = 128,
    skin_seed: int = 20801,
    eye_seed: int = 31991,
    brow_seed: int = 52081,
    lash_seed: int = 62081,
    scalp_hair_seed: int = 72081,
    scalp_underlay_seed: int = 82081,
) -> dict[str, object]:
    root = Path(output)
    root.mkdir(parents=True, exist_ok=True)

    upper_manifest = json.loads((UPPER_SEED / "seed-manifest.json").read_text(encoding="utf-8"))
    head_manifest = json.loads((HEAD_SEED / "seed-manifest.json").read_text(encoding="utf-8"))
    if upper_manifest["basemesh_id"] != "axm-hm08-upper-body-v0.1":
        raise ValueError("unexpected pinned upper-body basemesh")
    if head_manifest["basemesh_id"] != "axm-hm08-head-v0.2":
        raise ValueError("unexpected preferred head basemesh")

    upper_raw, upper_uv = read_obj_uv(UPPER_SEED / "upper_body.obj", name="hm08_upper_body_v0_1")
    upper_variant, upper_target_state = mix_targets(
        upper_raw,
        _library(UPPER_SEED),
        DEFAULT_WEIGHTS,
        name="sentinel_upper_body_identity_raw",
    )
    upper_m = scale(upper_variant, RAW_TO_M, name="sentinel_upper_body_identity_m")
    upper_uv_report = validate_uv(upper_m, upper_uv)
    if upper_uv_report["status"] != "pass":
        raise ValueError(f"upper-body UV invalid: {upper_uv_report}")

    head_raw, head_uv = read_obj_uv(HEAD_SEED / "head.obj", name="hm08_head_v0_2")
    head_variant, head_target_state = mix_targets(
        head_raw,
        _library(HEAD_SEED),
        DEFAULT_WEIGHTS,
        name="sentinel_head_identity_raw",
    )
    head_m = scale(head_variant, RAW_TO_M, name="sentinel_head_identity_m")
    head_uv_report = validate_uv(head_m, head_uv)
    if head_uv_report["status"] != "pass":
        raise ValueError(f"head UV invalid: {head_uv_report}")

    head_map = json.loads((HEAD_SEED / "source-index-map.json").read_text(encoding="utf-8"))
    upper_map = json.loads((UPPER_SEED / "source-index-map.json").read_text(encoding="utf-8"))
    overlap = _source_position_overlap(head_variant.vertices, upper_variant.vertices, head_map, upper_map)
    if overlap["status"] != "pass":
        raise ValueError(f"promoted head state drifted inside upper body: {overlap}")

    # Reuse the current physical face/eye authoring exactly. The physical skin
    # raster is generated from the head UV islands; neutral padding supplies a
    # deliberately plain body substrate until body-specific skin authoring is
    # built. This proves continuity without pretending torso skin is final.
    face_control = build_face_eyes_package(
        root,
        texture_size=texture_size,
        skin_seed=skin_seed,
        eye_seed=eye_seed,
        skin_mode="physical_v0.1",
    )
    if not all(face_control["acceptance"].values()):
        raise ValueError(f"preferred face control is not green: {face_control['acceptance']}")

    eye_metadata = json.loads((HEAD_SEED / "eye-landmarks.json").read_text(encoding="utf-8"))
    landmarks = derive_hm08_face_landmarks(head_variant, eye_metadata)
    radius_m = float(eye_metadata["prototype_eye_radius_m"])
    left_center = tuple(float(value) for value in eye_metadata["eyes"]["left"]["center_m"])
    right_center = tuple(float(value) for value in eye_metadata["eyes"]["right"]["center_m"])
    left_layers, left_uvs, left_eye_report = _translated_eye_layers(left_center, radius_m, side="left")
    right_layers, right_uvs, right_eye_report = _translated_eye_layers(right_center, radius_m, side="right")
    eye_layers = {
        layer: _combine_with_uv(
            [(left_layers[layer], left_uvs[layer]), (right_layers[layer], right_uvs[layer])],
            name=f"sentinel_upper_{layer}_pair",
        )
        for layer in ("sclera", "iris", "pupil", "cornea")
    }

    brows = generate_hm08_brows(head_m, landmarks_raw=landmarks, eye_metadata=eye_metadata, seed=brow_seed)
    brow_root = root / "textures" / "brows"
    brow_material = write_brow_material(
        brow_root,
        size=texture_size,
        seed=brow_seed,
        spec=BrowMaterialSpec(root_rgb=(29,21,18), tip_rgb=(43,31,25), density=0.58, roughness=0.58, filament_contrast=0.18),
    )
    brow_flat_normal_sha = _write_flat_normal(brow_root / "normal.png", texture_size)

    lashes = generate_hm08_upper_lashes(head_m, landmarks_raw=landmarks, eye_metadata=eye_metadata, seed=lash_seed)
    lash_root = root / "textures" / "lashes"
    lash_material = write_lash_material(
        lash_root,
        size=texture_size,
        seed=lash_seed,
        spec=LashMaterialSpec(root_rgb=(8,6,5), tip_rgb=(18,12,10), density=0.95, roughness=0.52),
    )
    lash_flat_normal_sha = _write_flat_normal(lash_root / "normal.png", texture_size)

    scalp_root_indices, scalp_cards, scalp_uv, scalp_hair = generate_hm08_short_scalp_hair(
        head_m,
        eye_metadata=eye_metadata,
        seed=scalp_hair_seed,
    )
    scalp_root = root / "textures" / "scalp_hair"
    scalp_material = write_hair_material(
        scalp_root,
        size=texture_size,
        seed=scalp_hair_seed,
        spec=HairMaterialSpec(
            root_rgb=(18, 12, 9),
            tip_rgb=(42, 29, 20),
            strand_count=40,
            roughness=0.48,
            alpha_cutoff_hint=0.12,
        ),
    )
    scalp_flat_normal_sha = _write_flat_normal(scalp_root / "normal.png", texture_size)

    scalp_underlay_mesh, scalp_underlay_uv, scalp_underlay = build_hm08_scalp_underlay(
        head_m,
        head_uv,
        eye_metadata=eye_metadata,
        offset_m=0.00035,
    )
    scalp_underlay_root = root / "textures" / "scalp_underlay"
    scalp_underlay_material = write_scalp_underlay_material(
        scalp_underlay_root,
        size=texture_size,
        seed=scalp_underlay_seed,
    )

    primitives = [
        MaterialPrimitive(upper_m, upper_uv, "AXM_Sentinel_UpperBody_Skin_Continuity_v0_1", "textures/skin/base_color.png", "textures/skin/normal.png", "textures/skin/orm.png", metallic_factor=0.0),
        MaterialPrimitive(eye_layers["sclera"][0], eye_layers["sclera"][1], "AXM_Eye_Sclera", "textures/eyes/sclera_base_color.png", "textures/eyes/sclera_normal.png", "textures/eyes/sclera_orm.png", metallic_factor=0.0),
        MaterialPrimitive(eye_layers["iris"][0], eye_layers["iris"][1], "AXM_Eye_Iris", "textures/eyes/iris_base_color.png", "textures/eyes/iris_normal.png", "textures/eyes/iris_orm.png", metallic_factor=0.0),
        MaterialPrimitive(eye_layers["pupil"][0], eye_layers["pupil"][1], "AXM_Eye_Pupil", "textures/eyes/pupil_base_color.png", "textures/eyes/pupil_normal.png", "textures/eyes/pupil_orm.png", metallic_factor=0.0, roughness_factor=0.24),
        MaterialPrimitive(eye_layers["cornea"][0], eye_layers["cornea"][1], "AXM_Eye_Cornea_Prototype", "textures/eyes/cornea_base_color.png", "textures/eyes/cornea_normal.png", "textures/eyes/cornea_orm.png", metallic_factor=0.0, roughness_factor=0.015, base_color_factor=(1.0,1.0,1.0,0.12), alpha_mode="BLEND"),
        MaterialPrimitive(brows.cards, brows.uvmap, "AXM_Sentinel_Brows_v0_3_Density", "textures/brows/base_color_alpha.png", "textures/brows/normal.png", "textures/brows/orm.png", metallic_factor=0.0, roughness_factor=1.0, double_sided=True, alpha_mode="BLEND"),
        MaterialPrimitive(lashes.cards, lashes.uvmap, "AXM_Sentinel_Upper_Lashes_v0_2", "textures/lashes/base_color_alpha.png", "textures/lashes/normal.png", "textures/lashes/orm.png", metallic_factor=0.0, roughness_factor=1.0, double_sided=True, alpha_mode="BLEND"),
        MaterialPrimitive(scalp_underlay_mesh, scalp_underlay_uv, "AXM_Sentinel_Short_Hair_RootMass_v0_1", "textures/scalp_underlay/base_color.png", "textures/scalp_underlay/normal.png", "textures/scalp_underlay/orm.png", metallic_factor=0.0, roughness_factor=1.0, double_sided=True),
        MaterialPrimitive(scalp_cards, scalp_uv, "AXM_Sentinel_Short_Hair_v0_2_Laid", "textures/scalp_hair/base_color_alpha.png", "textures/scalp_hair/normal.png", "textures/scalp_hair/orm.png", metallic_factor=0.0, roughness_factor=1.0, double_sided=True, alpha_mode="MASK", alpha_cutoff=0.12),
    ]
    delivery = write_multi_gltf(primitives, root, name=ASSET_NAME)
    document = json.loads((root / delivery["gltf"]).read_text(encoding="utf-8"))

    upper_weight_signature = [(row["name"], float(row["weight"])) for row in upper_target_state["applied"]]
    head_weight_signature = [(row["name"], float(row["weight"])) for row in head_target_state["applied"]]
    acceptance = {
        "pinned_upper_seed_green": all(upper_manifest["acceptance"].values()),
        "promoted_head_is_exact_source_subset": upper_manifest["relationship_to_head_seed"]["head_source_subset"] is True,
        "promoted_head_identity_zero_drift": overlap["status"] == "pass" and float(overlap["max_error_raw"]) <= 1e-12,
        "upper_body_expected_topology": len(upper_variant.vertices) == 10185 and len(upper_variant.faces) == 10158,
        "upper_body_uv_preserved": upper_uv_report["status"] == "pass",
        "head_uv_preserved": head_uv_report["status"] == "pass",
        "same_face_target_weights": upper_weight_signature == head_weight_signature,
        "preferred_face_control_green": face_control["skin_mode"] == "physical_v0.1" and all(face_control["acceptance"].values()),
        "source_grounded_eye_layers_valid": left_eye_report["status"] == "pass" and right_eye_report["status"] == "pass",
        "brow_route_valid": brows.evidence["truth"]["preferred_geometry_route"] is True,
        "lash_route_valid": lashes.evidence["schema"] == "axm.game-assets.hm08-upper-lashes.v0.2" and lashes.evidence["hair_validation"]["status"] == "pass",
        "hair_root_mass_and_cards_valid": scalp_underlay["uv_validation"]["status"] == "pass" and scalp_hair["unique_root_count"] == 320,
        "nine_semantic_primitives": delivery["primitive_count"] == 9,
        "nine_semantic_materials": delivery["material_count"] == 9,
        "body_skin_nonmetal": document["materials"][0]["pbrMetallicRoughness"]["metallicFactor"] == 0.0,
        "gltf_structural_valid": delivery["validation"]["status"] == "pass",
    }

    manifest: dict[str, object] = {
        "schema": SCHEMA,
        "asset": ASSET_NAME,
        "candidate_role": "continuous_human_upper_body_candidate",
        "coordinate_conversion": {"source_unit": "decimeter", "delivery_unit": "meter", "scale": RAW_TO_M},
        "upper_seed": {
            "basemesh_id": upper_manifest["basemesh_id"],
            "source_vertices": upper_manifest["extraction"]["compact_vertices"],
            "source_faces": upper_manifest["extraction"]["compact_faces"],
            "head_source_subset": upper_manifest["relationship_to_head_seed"],
        },
        "head_identity_overlap": overlap,
        "upper_target_mix": upper_target_state,
        "head_target_mix": head_target_state,
        "target_weight_signature": upper_weight_signature,
        "landmarks": landmark_packet(landmarks),
        "brows": brows.evidence,
        "brow_material": brow_material,
        "brow_flat_normal_sha256": brow_flat_normal_sha,
        "upper_lashes": lashes.evidence,
        "lash_material": lash_material,
        "lash_flat_normal_sha256": lash_flat_normal_sha,
        "short_scalp_hair": scalp_hair,
        "scalp_hair_root_indices": scalp_root_indices,
        "scalp_hair_material": scalp_material,
        "scalp_hair_flat_normal_sha256": scalp_flat_normal_sha,
        "scalp_underlay": scalp_underlay,
        "scalp_underlay_material": scalp_underlay_material,
        "face_control": {
            "skin_mode": face_control["skin_mode"],
            "skin": face_control["skin"],
            "eye_texture_receipts": face_control["eye_texture_receipts"],
        },
        "delivery": delivery,
        "acceptance": acceptance,
        "truth": {
            "production_body_claim": False,
            "production_body_skin_claim": False,
            "production_hair_claim": False,
            "high_end_character_claim": False,
            "notes": [
                "The human surface is one continuous hm08 topology from the pinned CC0 seed; the head is not glued onto a separate torso.",
                "All 4,197 promoted head source vertices are present in the upper body and the same facial target names/weights must produce zero positional drift on that overlap.",
                "Remapped target digests are expected to differ because compact vertex indices differ; name/weight equality plus source-position overlap is the correct continuity test.",
                "The physical face texture is reused on the original hm08 atlas. UV regions outside the authored head receive neutral padding and are therefore a continuity material, not finished body skin.",
                "Neutral hm08 torso/body proportions are a source substrate, not final Sentinel anatomy or musculature.",
                "Undersuit, armor, body rigging, deformation, hand/rifle contact and lower body remain later gates."
            ],
        },
    }
    payload = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8")
    (root / "upper-body-package.json").write_bytes(payload)
    manifest["manifest_sha256"] = _sha(payload)
    if not all(acceptance.values()):
        raise ValueError(f"current upper-body candidate failed: {acceptance}")
    return manifest


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("output", nargs="?", default="build/hm08-upper-body-current")
    parser.add_argument("--texture-size", type=int, default=128)
    args = parser.parse_args()
    result = build_current_upper_body_package(args.output, texture_size=args.texture_size)
    print(json.dumps({"acceptance": result["acceptance"], "overlap": result["head_identity_overlap"], "delivery": result["delivery"]}, indent=2))
