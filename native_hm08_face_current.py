#!/usr/bin/env python3
"""Current preferred Sentinel human-face candidate assembly.

Run 2 current state starts from the evidence-promoted components:
- repaired hm08 v0.2 topology + identity target mix
- physical-scale v0.1 skin
- source-grounded layered eyes
and adds the current source-grounded eyebrow-card candidate.

This file is intentionally the moving *candidate* assembler. Canonical source
organs remain separate and reconstructable; a visual layer only becomes
preferred after Godot evidence.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from native_hair_material import HairMaterialSpec, write_hair_material
from native_hm08_brows import generate_hm08_brows
from native_hm08_face_eyes import RAW_TO_M, SEED_ROOT, _combine_with_uv, _translated_eye_layers, build_face_eyes_package
from native_hm08_face_proof import DEFAULT_WEIGHTS
from native_hm08_landmarks import derive_hm08_face_landmarks, landmark_packet
from native_multi_gltf import MaterialPrimitive, write_multi_gltf
from native_pbr import png_bytes
from native_targets import load_target, mix_targets
from native_geometry import scale
from native_uv import read_obj_uv, validate_uv

SCHEMA = "axm.game-assets.hm08-face-current.v0.2"
ASSET_NAME = "sentinel_hm08_face_current_v0_2"


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
) -> dict[str, object]:
    root = Path(output)
    root.mkdir(parents=True, exist_ok=True)

    # Generate the currently preferred face/eye textures first. The current
    # candidate then recompiles those exact files plus the brow layer.
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

    # Placement remains the proven continuous-surface brow v0.2 mechanism.
    # These denser coverage parameters are *candidate* state only until the
    # real Godot close views justify promoting them into the brow organ default.
    brow_candidate = {
        "guides_per_brow": 24,
        "guide_length_m": 0.0050,
        "root_width_m": 0.00180,
        "tip_width_m": 0.00038,
        "root_offset_m": 0.00055,
    }
    brows = generate_hm08_brows(
        head_m,
        landmarks_raw=landmarks,
        eye_metadata=eye_metadata,
        seed=brow_seed,
        **brow_candidate,
    )
    brow_root = root / "textures" / "brows"
    brow_spec = HairMaterialSpec(
        root_rgb=(29, 21, 18),
        tip_rgb=(43, 31, 25),
        strand_count=8,
        roughness=0.56,
        alpha_cutoff_hint=0.18,
    )
    brow_material = write_hair_material(brow_root, size=texture_size, seed=brow_seed, spec=brow_spec)
    brow_flat_normal_sha = _write_flat_normal(brow_root / "normal.png", texture_size)

    primitives = [
        MaterialPrimitive(
            head_m, head_uv,
            "AXM_Sentinel_Skin_Physical_v0_1",
            "textures/skin/base_color.png",
            "textures/skin/normal.png",
            "textures/skin/orm.png",
            metallic_factor=0.0,
        ),
        MaterialPrimitive(
            eye_layers["sclera"][0], eye_layers["sclera"][1],
            "AXM_Eye_Sclera",
            "textures/eyes/sclera_base_color.png",
            "textures/eyes/sclera_normal.png",
            "textures/eyes/sclera_orm.png",
            metallic_factor=0.0,
        ),
        MaterialPrimitive(
            eye_layers["iris"][0], eye_layers["iris"][1],
            "AXM_Eye_Iris",
            "textures/eyes/iris_base_color.png",
            "textures/eyes/iris_normal.png",
            "textures/eyes/iris_orm.png",
            metallic_factor=0.0,
        ),
        MaterialPrimitive(
            eye_layers["pupil"][0], eye_layers["pupil"][1],
            "AXM_Eye_Pupil",
            "textures/eyes/pupil_base_color.png",
            "textures/eyes/pupil_normal.png",
            "textures/eyes/pupil_orm.png",
            metallic_factor=0.0,
            roughness_factor=0.24,
        ),
        MaterialPrimitive(
            eye_layers["cornea"][0], eye_layers["cornea"][1],
            "AXM_Eye_Cornea_Prototype",
            "textures/eyes/cornea_base_color.png",
            "textures/eyes/cornea_normal.png",
            "textures/eyes/cornea_orm.png",
            metallic_factor=0.0,
            roughness_factor=0.015,
            base_color_factor=(1.0, 1.0, 1.0, 0.12),
            alpha_mode="BLEND",
        ),
        MaterialPrimitive(
            brows.cards, brows.uvmap,
            "AXM_Sentinel_Brows_v0_2",
            "textures/brows/base_color_alpha.png",
            "textures/brows/normal.png",
            "textures/brows/orm.png",
            metallic_factor=0.0,
            roughness_factor=1.0,
            double_sided=True,
            # Hard MASK produced dotted on/off subpixel coverage in the first
            # 640 px Godot proof. BLEND preserves partial strand coverage while
            # the denser overlapping card groom is under visual evaluation.
            alpha_mode="BLEND",
        ),
    ]
    delivery = write_multi_gltf(primitives, root, name=ASSET_NAME)

    # Inspect glTF material truth rather than trusting our own requested spec.
    document = json.loads((root / delivery["gltf"]).read_text(encoding="utf-8"))
    brow_gltf_material = document["materials"][-1]
    skin_hashes = {name: control["skin"]["maps"][name]["sha256"] for name in ("base_color", "normal", "orm")}

    acceptance = {
        "preferred_physical_skin_control_green": control["skin_mode"] == "physical_v0.1" and all(control["acceptance"].values()),
        "repaired_identity_used": len(identity.vertices) == 4197 and len(identity_state["applied"]) == len(DEFAULT_WEIGHTS),
        "head_uv_preserved": head_uv_report["status"] == "pass",
        "source_grounded_eye_layers_valid": left_eye_report["status"] == "pass" and right_eye_report["status"] == "pass",
        "brow_guides_valid": brows.evidence["hair_validation"]["status"] == "pass",
        "brow_uv_valid": brows.evidence["uv_validation"]["status"] == "pass",
        "brow_surface_anchors_close": brows.evidence["max_root_surface_distance_m"] <= 0.00056,
        "brow_anchor_diversity": brows.evidence["unique_anchor_count"] >= 40,
        "brow_dense_candidate": brows.evidence["guide_count"] == 48 and brows.evidence["guides_per_brow"] == 24,
        "six_semantic_primitives": delivery["primitive_count"] == 6,
        "six_semantic_materials": delivery["material_count"] == 6,
        "brow_nonmetal": brow_gltf_material["pbrMetallicRoughness"]["metallicFactor"] == 0.0,
        "brow_alpha_blend": brow_gltf_material.get("alphaMode") == "BLEND" and "alphaCutoff" not in brow_gltf_material,
        "brow_double_sided": brow_gltf_material.get("doubleSided") is True,
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
        },
        "identity_target_mix": identity_state,
        "landmarks": landmark_packet(landmarks),
        "brow_candidate_parameters": brow_candidate,
        "brow_render_strategy": "dense_overlapping_cards_with_alpha_blend",
        "brows": brows.evidence,
        "brow_material": brow_material,
        "brow_flat_normal_sha256": brow_flat_normal_sha,
        "delivery": delivery,
        "acceptance": acceptance,
        "truth": {
            "preferred_brow_claim": False,
            "high_end_character_claim": False,
            "notes": [
                "Brow v0.2 candidate preserves the proven continuous-surface placement mechanism and changes only coverage/groom density plus alpha handling.",
                "The first 32-guide MASK render read as dotted guide marks; this denser BLEND candidate explicitly targets that measured minification failure.",
                "Source-grounded placement and technical validity do not imply aesthetic promotion; real Godot close views decide that.",
                "This candidate assembler is expected to evolve with lashes, scalp hair and later neck/torso while source organs remain separate."
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
    print(json.dumps({"acceptance": result["acceptance"], "brows": result["brows"], "delivery": result["delivery"]}, indent=2))
