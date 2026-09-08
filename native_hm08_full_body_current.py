#!/usr/bin/env python3
"""Current equipped Sentinel body candidate.

The pinned hm08 body stays canonical. The promoted face/eyes/hair, graphite
undersuit, and segmented rigid armor remain separate state layers. v0.4 adds
source-derived glove/boot uppers and independent rubber soles so extremity gear
is reconstructable and replaceable rather than baked into human topology.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from native_geometry import scale
from native_hair_material import HairMaterialSpec, write_hair_material
from native_hm08_brow_material import BrowMaterialSpec, write_brow_material
from native_hm08_brows import generate_hm08_brows
from native_hm08_extremity_gear import build_hm08_extremity_gear, write_sentinel_extremity_materials
from native_hm08_face_eyes import RAW_TO_M, _combine_with_uv, _translated_eye_layers, build_face_eyes_package
from native_hm08_face_proof import DEFAULT_WEIGHTS
from native_hm08_landmarks import derive_hm08_face_landmarks, landmark_packet
from native_hm08_lash_material import LashMaterialSpec, write_lash_material
from native_hm08_lashes import generate_hm08_upper_lashes
from native_hm08_scalp_hair import generate_hm08_short_scalp_hair
from native_hm08_scalp_underlay import build_hm08_scalp_underlay, write_scalp_underlay_material
from native_hm08_sentinel_armor import build_sentinel_rigid_armor, write_sentinel_armor_materials
from native_hm08_undersuit import build_hm08_undersuit, write_sentinel_undersuit_material
from native_hm08_upper_body_current import _source_position_overlap
from native_multi_gltf import MaterialPrimitive, write_multi_gltf
from native_pbr import png_bytes
from native_targets import load_target, mix_targets
from native_uv import read_obj_uv, validate_uv

HEAD_SEED = Path("seed_data/hm08_head_v0.2")
UPPER_SEED = Path("seed_data/hm08_upper_body_v0.1")
FULL_SEED = Path("seed_data/hm08_full_body_v0.1")
SCHEMA = "axm.game-assets.hm08-full-body-current.v0.4"
ASSET_NAME = "sentinel_hm08_full_body_current_v0_4"


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


def _weight_signature(state: dict[str, object]):
    return [(row["name"], float(row["weight"])) for row in state["applied"]]


def build_current_full_body_package(
    output: str | Path,
    *,
    texture_size: int = 128,
    skin_seed: int = 20801,
    eye_seed: int = 31991,
    brow_seed: int = 52081,
    lash_seed: int = 62081,
    scalp_hair_seed: int = 72081,
    scalp_underlay_seed: int = 82081,
    undersuit_seed: int = 91021,
    armor_seed: int = 93021,
    extremity_seed: int = 95021,
) -> dict[str, object]:
    root = Path(output)
    root.mkdir(parents=True, exist_ok=True)

    full_manifest = json.loads((FULL_SEED / "seed-manifest.json").read_text(encoding="utf-8"))
    if full_manifest["basemesh_id"] != "axm-hm08-full-body-v0.1":
        raise ValueError("unexpected pinned full-body basemesh")

    full_raw, full_uv = read_obj_uv(FULL_SEED / "body.obj", name="hm08_full_body_v0_1")
    full_variant, full_target_state = mix_targets(
        full_raw, _library(FULL_SEED), DEFAULT_WEIGHTS, name="sentinel_full_body_identity_raw"
    )
    full_m = scale(full_variant, RAW_TO_M, name="sentinel_full_body_identity_m")
    full_uv_report = validate_uv(full_m, full_uv)
    if full_uv_report["status"] != "pass":
        raise ValueError(f"full-body UV invalid: {full_uv_report}")

    upper_raw, _upper_uv = read_obj_uv(UPPER_SEED / "upper_body.obj", name="hm08_upper_body_v0_1")
    upper_variant, upper_target_state = mix_targets(
        upper_raw, _library(UPPER_SEED), DEFAULT_WEIGHTS, name="sentinel_upper_body_identity_raw"
    )
    head_raw, head_uv = read_obj_uv(HEAD_SEED / "head.obj", name="hm08_head_v0_2")
    head_variant, head_target_state = mix_targets(
        head_raw, _library(HEAD_SEED), DEFAULT_WEIGHTS, name="sentinel_head_identity_raw"
    )
    head_m = scale(head_variant, RAW_TO_M, name="sentinel_head_identity_m")
    head_uv_report = validate_uv(head_m, head_uv)
    if head_uv_report["status"] != "pass":
        raise ValueError(f"head UV invalid: {head_uv_report}")

    full_map = json.loads((FULL_SEED / "source-index-map.json").read_text(encoding="utf-8"))
    upper_map = json.loads((UPPER_SEED / "source-index-map.json").read_text(encoding="utf-8"))
    head_map = json.loads((HEAD_SEED / "source-index-map.json").read_text(encoding="utf-8"))
    head_overlap = _source_position_overlap(head_variant.vertices, full_variant.vertices, head_map, full_map)
    upper_overlap = _source_position_overlap(upper_variant.vertices, full_variant.vertices, upper_map, full_map)
    if head_overlap["status"] != "pass" or upper_overlap["status"] != "pass":
        raise ValueError(f"full body drifted from promoted substrates: head={head_overlap} upper={upper_overlap}")

    signatures = {
        "head": _weight_signature(head_target_state),
        "upper_body": _weight_signature(upper_target_state),
        "full_body": _weight_signature(full_target_state),
    }
    if not (signatures["head"] == signatures["upper_body"] == signatures["full_body"]):
        raise ValueError(f"facial target semantics drifted across source topologies: {signatures}")

    face_control = build_face_eyes_package(
        root, texture_size=texture_size, skin_seed=skin_seed, eye_seed=eye_seed, skin_mode="physical_v0.1"
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
            name=f"sentinel_full_{layer}_pair",
        )
        for layer in ("sclera", "iris", "pupil", "cornea")
    }

    brows = generate_hm08_brows(head_m, landmarks_raw=landmarks, eye_metadata=eye_metadata, seed=brow_seed)
    brow_root = root / "textures" / "brows"
    brow_material = write_brow_material(
        brow_root, size=texture_size, seed=brow_seed,
        spec=BrowMaterialSpec(root_rgb=(29,21,18), tip_rgb=(43,31,25), density=0.58, roughness=0.58, filament_contrast=0.18),
    )
    brow_flat_normal_sha = _write_flat_normal(brow_root / "normal.png", texture_size)

    lashes = generate_hm08_upper_lashes(head_m, landmarks_raw=landmarks, eye_metadata=eye_metadata, seed=lash_seed)
    lash_root = root / "textures" / "lashes"
    lash_material = write_lash_material(
        lash_root, size=texture_size, seed=lash_seed,
        spec=LashMaterialSpec(root_rgb=(8,6,5), tip_rgb=(18,12,10), density=0.95, roughness=0.52),
    )
    lash_flat_normal_sha = _write_flat_normal(lash_root / "normal.png", texture_size)

    scalp_root_indices, scalp_cards, scalp_uv, scalp_hair = generate_hm08_short_scalp_hair(
        head_m, eye_metadata=eye_metadata, seed=scalp_hair_seed
    )
    scalp_root = root / "textures" / "scalp_hair"
    scalp_material = write_hair_material(
        scalp_root, size=texture_size, seed=scalp_hair_seed,
        spec=HairMaterialSpec(
            root_rgb=(18,12,9), tip_rgb=(42,29,20), strand_count=40,
            roughness=0.48, alpha_cutoff_hint=0.12,
        ),
    )
    scalp_flat_normal_sha = _write_flat_normal(scalp_root / "normal.png", texture_size)

    scalp_underlay_mesh, scalp_underlay_uv, scalp_underlay = build_hm08_scalp_underlay(
        head_m, head_uv, eye_metadata=eye_metadata, offset_m=0.00035
    )
    scalp_underlay_root = root / "textures" / "scalp_underlay"
    scalp_underlay_material = write_scalp_underlay_material(
        scalp_underlay_root, size=texture_size, seed=scalp_underlay_seed
    )

    undersuit_mesh, undersuit_uv, undersuit = build_hm08_undersuit(full_m, full_uv)
    undersuit_root = root / "textures" / "undersuit"
    undersuit_material = write_sentinel_undersuit_material(
        undersuit_root, size=texture_size, seed=undersuit_seed
    )

    armor_primary, armor_primary_uv, armor_accent, armor_accent_uv, armor = build_sentinel_rigid_armor(full_m)
    armor_materials = write_sentinel_armor_materials(
        root / "textures" / "armor", size=texture_size, seed=armor_seed
    )

    extremity_shell, extremity_uv, boot_soles, boot_sole_uv, extremity = build_hm08_extremity_gear(full_m, full_uv)
    extremity_materials = write_sentinel_extremity_materials(
        root / "textures" / "extremity", size=texture_size, seed=extremity_seed
    )

    primitives = [
        MaterialPrimitive(full_m, full_uv, "AXM_Sentinel_FullBody_Skin_Continuity_v0_1", "textures/skin/base_color.png", "textures/skin/normal.png", "textures/skin/orm.png", metallic_factor=0.0),
        MaterialPrimitive(undersuit_mesh, undersuit_uv, "AXM_Sentinel_Graphite_Undersuit_v0_1", "textures/undersuit/base_color.png", "textures/undersuit/normal.png", "textures/undersuit/orm.png", metallic_factor=0.0, roughness_factor=1.0, double_sided=True),
        MaterialPrimitive(armor_primary, armor_primary_uv, "AXM_Sentinel_Armor_Primary_v0_2", "textures/armor/primary/base_color.png", "textures/armor/primary/normal.png", "textures/armor/primary/orm.png", metallic_factor=1.0, roughness_factor=1.0),
        MaterialPrimitive(armor_accent, armor_accent_uv, "AXM_Sentinel_Armor_Accent_v0_2", "textures/armor/accent/base_color.png", "textures/armor/accent/normal.png", "textures/armor/accent/orm.png", metallic_factor=1.0, roughness_factor=1.0),
        MaterialPrimitive(extremity_shell, extremity_uv, "AXM_Sentinel_Gloves_BootUppers_v0_1", "textures/extremity/textile/base_color.png", "textures/extremity/textile/normal.png", "textures/extremity/textile/orm.png", metallic_factor=0.0, roughness_factor=1.0, double_sided=True),
        MaterialPrimitive(boot_soles, boot_sole_uv, "AXM_Sentinel_BootSoles_v0_1", "textures/extremity/rubber/base_color.png", "textures/extremity/rubber/normal.png", "textures/extremity/rubber/orm.png", metallic_factor=0.0, roughness_factor=1.0),
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

    acceptance = {
        "pinned_full_seed_green": all(full_manifest["acceptance"].values()),
        "full_body_closed_source": full_manifest["extraction"]["compact_vertices"] == 13380 and full_manifest["extraction"]["compact_faces"] == 13378,
        "head_identity_zero_drift": head_overlap["status"] == "pass" and float(head_overlap["max_error_raw"]) <= 1e-12,
        "upper_body_identity_zero_drift": upper_overlap["status"] == "pass" and float(upper_overlap["max_error_raw"]) <= 1e-12,
        "full_body_uv_preserved": full_uv_report["status"] == "pass",
        "head_uv_preserved": head_uv_report["status"] == "pass",
        "same_face_target_semantics": signatures["head"] == signatures["upper_body"] == signatures["full_body"],
        "preferred_face_control_green": face_control["skin_mode"] == "physical_v0.1" and all(face_control["acceptance"].values()),
        "source_grounded_eye_layers_valid": left_eye_report["status"] == "pass" and right_eye_report["status"] == "pass",
        "brow_route_valid": brows.evidence["truth"]["preferred_geometry_route"] is True,
        "lash_route_valid": lashes.evidence["schema"] == "axm.game-assets.hm08-upper-lashes.v0.2" and lashes.evidence["hair_validation"]["status"] == "pass",
        "hair_root_mass_and_cards_valid": scalp_underlay["uv_validation"]["status"] == "pass" and scalp_hair["unique_root_count"] == 320,
        "undersuit_source_grounded": undersuit["truth"]["source_grounded"] is True and undersuit["uv_validation"]["status"] == "pass",
        "undersuit_surface_coverage": undersuit["surface_coverage_fraction"] >= undersuit["minimum_surface_coverage"] and undersuit["surface_coverage_fraction"] > 0.70,
        "undersuit_topology_valid": undersuit["topology"]["invalid_indices"] == 0 and undersuit["topology"]["degenerate_faces"] == 0 and undersuit["topology"]["nonmanifold_edges"] == 0,
        "armor_body_grounded": armor["truth"]["body_grounded"] is True and armor["schema"] == "axm.game-assets.hm08-sentinel-rigid-armor.v0.2" and armor["primary_component_count"] >= 20 and armor["accent_component_count"] >= 12,
        "armor_topology_valid": armor["primary_topology"]["invalid_indices"] == 0 and armor["primary_topology"]["degenerate_faces"] == 0 and armor["primary_topology"]["nonmanifold_edges"] == 0 and armor["accent_topology"]["invalid_indices"] == 0 and armor["accent_topology"]["degenerate_faces"] == 0 and armor["accent_topology"]["nonmanifold_edges"] == 0,
        "armor_uv_valid": armor["primary_uv_validation"]["status"] == "pass" and armor["accent_uv_validation"]["status"] == "pass",
        "extremity_source_grounded": extremity["truth"]["source_grounded"] is True and extremity["truth"]["canonical_body_mutated"] is False,
        "extremity_shell_valid": extremity["shell_uv_validation"]["status"] == "pass" and extremity["shell_topology"]["invalid_indices"] == 0 and extremity["shell_topology"]["degenerate_faces"] == 0 and extremity["shell_topology"]["nonmanifold_edges"] == 0,
        "boot_soles_valid": extremity["sole_uv_validation"]["status"] == "pass" and extremity["sole_topology"]["closed_two_manifold_candidate"] is True,
        "fourteen_semantic_primitives": delivery["primitive_count"] == 14,
        "fourteen_semantic_materials": delivery["material_count"] == 14,
        "body_skin_nonmetal": document["materials"][0]["pbrMetallicRoughness"]["metallicFactor"] == 0.0,
        "undersuit_nonmetal": document["materials"][1]["pbrMetallicRoughness"]["metallicFactor"] == 0.0,
        "armor_metallic_channels_enabled": document["materials"][2]["pbrMetallicRoughness"]["metallicFactor"] == 1.0 and document["materials"][3]["pbrMetallicRoughness"]["metallicFactor"] == 1.0,
        "extremity_nonmetal": document["materials"][4]["pbrMetallicRoughness"]["metallicFactor"] == 0.0 and document["materials"][5]["pbrMetallicRoughness"]["metallicFactor"] == 0.0,
        "gltf_structural_valid": delivery["validation"]["status"] == "pass",
    }

    manifest: dict[str, object] = {
        "schema": SCHEMA,
        "asset": ASSET_NAME,
        "candidate_role": "sentinel_equipped_body_candidate",
        "coordinate_conversion": {"source_unit":"decimeter","delivery_unit":"meter","scale":RAW_TO_M},
        "full_seed": {
            "basemesh_id": full_manifest["basemesh_id"],
            "source_vertices": full_manifest["extraction"]["compact_vertices"],
            "source_faces": full_manifest["extraction"]["compact_faces"],
            "source_bounds": full_manifest["extraction"]["compact_actual_bounds"],
            "relationships": full_manifest["relationship_to_promoted_substrates"],
        },
        "head_identity_overlap": head_overlap,
        "upper_body_identity_overlap": upper_overlap,
        "target_weight_signatures": signatures,
        "landmarks": landmark_packet(landmarks),
        "undersuit": undersuit,
        "undersuit_material": undersuit_material,
        "rigid_armor": armor,
        "rigid_armor_materials": armor_materials,
        "extremity_gear": extremity,
        "extremity_materials": extremity_materials,
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
            "production_undersuit_claim": False,
            "production_armor_claim": False,
            "production_extremity_gear_claim": False,
            "rigged_character_claim": False,
            "high_end_character_claim": False,
            "notes": [
                "The complete closed human substrate remains untouched underneath all wearable layers.",
                "Segmented armor v0.2 replaces the visually rejected slab-style torso while preserving separately editable primary/accent component groups.",
                "Gloves and boot uppers are source-derived textile shells; boot soles are independent nonmetal closed geometry, so hands/feet no longer require baked skin edits.",
                "This is still a static equipment/readability gate. Production quality still requires glove/boot panel detail, sole tread, pose clearance, articulation and deformation evidence.",
                "Rifle contact, locomotion, facial motion and LOD remain later gates."
            ],
        },
    }
    payload = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8")
    (root / "full-body-package.json").write_bytes(payload)
    manifest["manifest_sha256"] = _sha(payload)
    if not all(acceptance.values()):
        raise ValueError(f"current full-body candidate failed: {acceptance}")
    return manifest


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("output", nargs="?", default="build/hm08-full-body-current")
    parser.add_argument("--texture-size", type=int, default=128)
    args = parser.parse_args()
    result = build_current_full_body_package(args.output, texture_size=args.texture_size)
    print(json.dumps({
        "acceptance": result["acceptance"],
        "head_overlap": result["head_identity_overlap"],
        "upper_overlap": result["upper_body_identity_overlap"],
        "undersuit": result["undersuit"],
        "armor": result["rigid_armor"],
        "extremity_gear": result["extremity_gear"],
        "delivery": result["delivery"],
    }, indent=2))
