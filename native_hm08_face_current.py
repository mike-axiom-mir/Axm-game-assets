#!/usr/bin/env python3
"""Current preferred Sentinel human-face candidate assembly.

Current preferred substrate:
- repaired hm08 v0.2 topology + identity target mix
- physical-scale v0.1 skin
- source-grounded layered eyes
- brow v0.3 geometry + dedicated density material
- upper-lash v0.2 geometry/material after Godot repair

v0.6 adds short scalp hair as the only new visual layer.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from native_hair_material import HairMaterialSpec, write_hair_material
from native_hm08_brow_material import BrowMaterialSpec, write_brow_material
from native_hm08_brows import generate_hm08_brows
from native_hm08_face_eyes import RAW_TO_M, SEED_ROOT, _combine_with_uv, _translated_eye_layers, build_face_eyes_package
from native_hm08_face_proof import DEFAULT_WEIGHTS
from native_hm08_landmarks import derive_hm08_face_landmarks, landmark_packet
from native_hm08_lash_material import LashMaterialSpec, write_lash_material
from native_hm08_lashes import generate_hm08_upper_lashes
from native_hm08_scalp_hair import generate_hm08_short_scalp_hair
from native_multi_gltf import MaterialPrimitive, write_multi_gltf
from native_pbr import png_bytes
from native_targets import load_target, mix_targets
from native_geometry import scale
from native_uv import read_obj_uv, validate_uv

SCHEMA = "axm.game-assets.hm08-face-current.v0.6"
ASSET_NAME = "sentinel_hm08_face_current_v0_6"


def _sha(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _write_flat_normal(path: Path, size: int) -> str:
    data = png_bytes(size, size, 3, bytes((128, 128, 255)) * (size * size))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return _sha(data)


def build_current_face_package(
    output: str | Path,
    *,
    texture_size: int = 128,
    skin_seed: int = 20801,
    eye_seed: int = 31991,
    brow_seed: int = 52081,
    lash_seed: int = 62081,
    scalp_hair_seed: int = 72081,
) -> dict[str, object]:
    root = Path(output)
    root.mkdir(parents=True, exist_ok=True)

    control = build_face_eyes_package(
        root,
        texture_size=texture_size,
        skin_seed=skin_seed,
        eye_seed=eye_seed,
        skin_mode="physical_v0.1",
    )
    if not all(control["acceptance"].values()):
        raise ValueError(f"preferred physical face control is not green: {control['acceptance']}")

    raw_head, head_uv = read_obj_uv(SEED_ROOT / "head.obj", name="hm08_head_v0_2")
    library = {
        name: load_target(SEED_ROOT / "targets" / f"{name}.target", license="CC0-source-remap")
        for name in sorted(DEFAULT_WEIGHTS)
    }
    identity, identity_state = mix_targets(raw_head, library, DEFAULT_WEIGHTS, name="sentinel_current_identity")
    head_m = scale(identity, RAW_TO_M, name="sentinel_current_head_m")
    head_uv_report = validate_uv(head_m, head_uv)
    if head_uv_report["status"] != "pass":
        raise ValueError(f"current-face head UV invalid: {head_uv_report}")

    eye_metadata = json.loads((SEED_ROOT / "eye-landmarks.json").read_text(encoding="utf-8"))
    landmarks = derive_hm08_face_landmarks(identity, eye_metadata)
    radius_m = float(eye_metadata["prototype_eye_radius_m"])
    left_center = tuple(float(value) for value in eye_metadata["eyes"]["left"]["center_m"])
    right_center = tuple(float(value) for value in eye_metadata["eyes"]["right"]["center_m"])
    left_layers, left_uvs, left_eye_report = _translated_eye_layers(left_center, radius_m, side="left")
    right_layers, right_uvs, right_eye_report = _translated_eye_layers(right_center, radius_m, side="right")
    eye_layers = {
        layer: _combine_with_uv(
            [(left_layers[layer], left_uvs[layer]), (right_layers[layer], right_uvs[layer])],
            name=f"sentinel_current_{layer}_pair",
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

    rooted_hair, scalp_cards, scalp_uv, scalp_hair = generate_hm08_short_scalp_hair(
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
            root_rgb=(24, 16, 12),
            tip_rgb=(50, 35, 25),
            strand_count=18,
            roughness=0.46,
            alpha_cutoff_hint=0.28,
        ),
    )
    scalp_flat_normal_sha = _write_flat_normal(scalp_root / "normal.png", texture_size)

    primitives = [
        MaterialPrimitive(head_m, head_uv, "AXM_Sentinel_Skin_Physical_v0_1", "textures/skin/base_color.png", "textures/skin/normal.png", "textures/skin/orm.png", metallic_factor=0.0),
        MaterialPrimitive(eye_layers["sclera"][0], eye_layers["sclera"][1], "AXM_Eye_Sclera", "textures/eyes/sclera_base_color.png", "textures/eyes/sclera_normal.png", "textures/eyes/sclera_orm.png", metallic_factor=0.0),
        MaterialPrimitive(eye_layers["iris"][0], eye_layers["iris"][1], "AXM_Eye_Iris", "textures/eyes/iris_base_color.png", "textures/eyes/iris_normal.png", "textures/eyes/iris_orm.png", metallic_factor=0.0),
        MaterialPrimitive(eye_layers["pupil"][0], eye_layers["pupil"][1], "AXM_Eye_Pupil", "textures/eyes/pupil_base_color.png", "textures/eyes/pupil_normal.png", "textures/eyes/pupil_orm.png", metallic_factor=0.0, roughness_factor=0.24),
        MaterialPrimitive(eye_layers["cornea"][0], eye_layers["cornea"][1], "AXM_Eye_Cornea_Prototype", "textures/eyes/cornea_base_color.png", "textures/eyes/cornea_normal.png", "textures/eyes/cornea_orm.png", metallic_factor=0.0, roughness_factor=0.015, base_color_factor=(1.0,1.0,1.0,0.12), alpha_mode="BLEND"),
        MaterialPrimitive(brows.cards, brows.uvmap, "AXM_Sentinel_Brows_v0_3_Density", "textures/brows/base_color_alpha.png", "textures/brows/normal.png", "textures/brows/orm.png", metallic_factor=0.0, roughness_factor=1.0, double_sided=True, alpha_mode="BLEND"),
        MaterialPrimitive(lashes.cards, lashes.uvmap, "AXM_Sentinel_Upper_Lashes_v0_2", "textures/lashes/base_color_alpha.png", "textures/lashes/normal.png", "textures/lashes/orm.png", metallic_factor=0.0, roughness_factor=1.0, double_sided=True, alpha_mode="BLEND"),
        MaterialPrimitive(scalp_cards, scalp_uv, "AXM_Sentinel_Short_Hair_v0_1", "textures/scalp_hair/base_color_alpha.png", "textures/scalp_hair/normal.png", "textures/scalp_hair/orm.png", metallic_factor=0.0, roughness_factor=1.0, double_sided=True, alpha_mode="MASK", alpha_cutoff=0.28),
    ]
    delivery = write_multi_gltf(primitives, root, name=ASSET_NAME)

    document = json.loads((root / delivery["gltf"]).read_text(encoding="utf-8"))
    brow_gltf_material = document["materials"][-3]
    lash_gltf_material = document["materials"][-2]
    scalp_gltf_material = document["materials"][-1]
    skin_hashes = {name: control["skin"]["maps"][name]["sha256"] for name in ("base_color", "normal", "orm")}

    acceptance = {
        "preferred_physical_skin_control_green": control["skin_mode"] == "physical_v0.1" and all(control["acceptance"].values()),
        "repaired_identity_used": len(identity.vertices) == 4197 and len(identity_state["applied"]) == len(DEFAULT_WEIGHTS),
        "head_uv_preserved": head_uv_report["status"] == "pass",
        "source_grounded_eye_layers_valid": left_eye_report["status"] == "pass" and right_eye_report["status"] == "pass",
        "preferred_brow_route_valid": brows.evidence["truth"]["preferred_geometry_route"] is True and brow_material["coverage_evidence"]["mean_alpha"] > 0.20,
        "preferred_lash_v0_2_valid": lashes.evidence["schema"] == "axm.game-assets.hm08-upper-lashes.v0.2" and lashes.evidence["hair_validation"]["status"] == "pass" and lash_material["schema"] == "axm.game-assets.lash-ribbon-material.v0.2",
        "scalp_root_pool_sufficient": scalp_hair["root_selection"]["candidate_count"] >= 256,
        "scalp_roots_unique": scalp_hair["unique_root_count"] == 256,
        "scalp_crown_and_back_present": scalp_hair["selected_crown_roots"] >= 40 and scalp_hair["selected_back_side_roots"] >= 40,
        "scalp_spans_both_sides": scalp_hair["root_x_range_m"][0] < 0.0 < scalp_hair["root_x_range_m"][1],
        "scalp_depth_coverage": scalp_hair["root_z_span_m"] > 0.06,
        "scalp_guides_valid": scalp_hair["hair_validation"]["status"] == "pass" and scalp_hair["uv_validation"]["status"] == "pass",
        "eight_semantic_primitives": delivery["primitive_count"] == 8,
        "eight_semantic_materials": delivery["material_count"] == 8,
        "brow_nonmetal_blend": brow_gltf_material["pbrMetallicRoughness"]["metallicFactor"] == 0.0 and brow_gltf_material.get("alphaMode") == "BLEND",
        "lash_nonmetal_blend": lash_gltf_material["pbrMetallicRoughness"]["metallicFactor"] == 0.0 and lash_gltf_material.get("alphaMode") == "BLEND",
        "scalp_hair_nonmetal_mask": scalp_gltf_material["pbrMetallicRoughness"]["metallicFactor"] == 0.0 and scalp_gltf_material.get("alphaMode") == "MASK" and abs(float(scalp_gltf_material.get("alphaCutoff", 0.0)) - 0.28) < 1e-9,
        "gltf_structural_valid": delivery["validation"]["status"] == "pass",
    }
    manifest: dict[str, object] = {
        "schema": SCHEMA,
        "asset": ASSET_NAME,
        "candidate_role": "current_face_candidate",
        "base_preferred_state": {
            "head_seed": "axm-hm08-head-v0.2",
            "skin_mode": "physical_v0.1",
            "skin_map_hashes": skin_hashes,
            "eyes": "source_grounded_hm08_helper_geometry",
            "brows": "hm08-brows.v0.3 + brow-density-material.v0.1",
            "upper_lashes": "hm08-upper-lashes.v0.2 + lash-ribbon-material.v0.2",
        },
        "identity_target_mix": identity_state,
        "landmarks": landmark_packet(landmarks),
        "brows": brows.evidence,
        "brow_material": brow_material,
        "brow_flat_normal_sha256": brow_flat_normal_sha,
        "upper_lashes": lashes.evidence,
        "lash_material": lash_material,
        "lash_flat_normal_sha256": lash_flat_normal_sha,
        "short_scalp_hair": scalp_hair,
        "scalp_hair_root_indices": rooted_hair.root_indices,
        "scalp_hair_material": scalp_material,
        "scalp_hair_flat_normal_sha256": scalp_flat_normal_sha,
        "delivery": delivery,
        "acceptance": acceptance,
        "truth": {
            "preferred_brow_route": True,
            "preferred_lash_route": True,
            "preferred_scalp_hair_claim": False,
            "high_end_character_claim": False,
            "notes": [
                "Brow v0.3 and upper-lash v0.2 are held fixed from their Godot evidence while short scalp hair is the only new visual layer.",
                "Scalp hair v0.1 uses 256 unique canonical hm08 roots selected from a crown plus behind-eye back/side region; alpha MASK avoids large-card transparency sorting.",
                "Hairline shape, temple transitions, card coverage and final groom quality still require real Godot close-view judgment.",
                "Neck/torso integration remains the next structural layer after a usable hair route."
            ],
        },
    }
    payload = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8")
    (root / "current-face-package.json").write_bytes(payload)
    manifest["manifest_sha256"] = _sha(payload)
    if not all(acceptance.values()):
        raise ValueError(f"current face candidate failed: {acceptance}")
    return manifest


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("output", nargs="?", default="build/hm08-face-current")
    parser.add_argument("--texture-size", type=int, default=128)
    args = parser.parse_args()
    result = build_current_face_package(args.output, texture_size=args.texture_size)
    print(json.dumps({"acceptance": result["acceptance"], "short_scalp_hair": result["short_scalp_hair"], "delivery": result["delivery"]}, indent=2))
