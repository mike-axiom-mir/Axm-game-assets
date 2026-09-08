#!/usr/bin/env python3
"""Parallel hm08 face+eyes package with AXM-native secondary facial forms.

This is an A/B candidate against the known-good generic-skin/source-grounded-eye
package. It deliberately changes geometry only: same identity targets, skin
material, eye geometry/material, units and delivery compiler.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from native_hm08_face_eyes import (
    RAW_TO_M,
    SEED_ROOT,
    _combine_with_uv,
    _translated_eye_layers,
    build_face_eyes_package,
)
from native_hm08_face_proof import DEFAULT_WEIGHTS
from native_hm08_landmarks import derive_hm08_face_landmarks, landmark_packet
from native_hm08_secondary_forms import apply_secondary_forms, displacement_report
from native_multi_gltf import MaterialPrimitive, write_multi_gltf
from native_targets import load_target, mix_targets
from native_geometry import scale
from native_uv import read_obj_uv, validate_uv

SCHEMA = "axm.game-assets.hm08-face-secondary.v0.1"
ASSET_NAME = "sentinel_hm08_face_eyes_secondary_v0_1"


def _sha(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def build_face_secondary_package(
    output: str | Path,
    *,
    texture_size: int = 128,
    skin_seed: int = 20801,
    eye_seed: int = 31991,
) -> dict[str, object]:
    root = Path(output)
    root.mkdir(parents=True, exist_ok=True)

    # First build the known-good generic control into the same isolated output
    # so all texture bytes/eye choices are identical. The secondary candidate
    # then recompiles geometry while referencing those exact generated maps.
    control = build_face_eyes_package(
        root,
        texture_size=texture_size,
        skin_seed=skin_seed,
        eye_seed=eye_seed,
        skin_mode="generic",
    )

    raw_head, head_uv = read_obj_uv(SEED_ROOT / "head.obj", name="hm08_head_v0_2")
    library = {
        name: load_target(SEED_ROOT / "targets" / f"{name}.target", license="CC0-source-remap")
        for name in sorted(DEFAULT_WEIGHTS)
    }
    identity_variant, identity_state = mix_targets(
        raw_head,
        library,
        DEFAULT_WEIGHTS,
        name="sentinel_identity_before_secondary",
    )
    eye_metadata = json.loads((SEED_ROOT / "eye-landmarks.json").read_text(encoding="utf-8"))
    landmarks = derive_hm08_face_landmarks(identity_variant, eye_metadata)
    secondary_raw, secondary_targets, secondary_state = apply_secondary_forms(
        identity_variant,
        landmarks,
        eye_metadata,
        name="sentinel_identity_secondary_v0_1",
    )
    displacement = displacement_report(identity_variant, secondary_raw)
    head_m = scale(secondary_raw, RAW_TO_M, name="sentinel_face_secondary_meters")
    head_uv_report = validate_uv(head_m, head_uv)
    if head_uv_report["status"] != "pass":
        raise ValueError(f"secondary-form meter delivery broke head UV state: {head_uv_report}")

    radius_m = float(eye_metadata["prototype_eye_radius_m"])
    left_center = tuple(float(value) for value in eye_metadata["eyes"]["left"]["center_m"])
    right_center = tuple(float(value) for value in eye_metadata["eyes"]["right"]["center_m"])
    left_layers, left_uvs, left_report = _translated_eye_layers(left_center, radius_m, side="left")
    right_layers, right_uvs, right_report = _translated_eye_layers(right_center, radius_m, side="right")
    layer_meshes = {
        layer: _combine_with_uv(
            [(left_layers[layer], left_uvs[layer]), (right_layers[layer], right_uvs[layer])],
            name=f"sentinel_{layer}_pair_secondary_control",
        )
        for layer in ("sclera", "iris", "pupil", "cornea")
    }

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
    delivery = write_multi_gltf(primitives, root, name=ASSET_NAME)

    control_textures = {
        name: item["sha256"]
        for name, item in control["skin"]["maps"].items()
        if name in {"base_color", "normal", "orm"}
    }
    acceptance = {
        "control_package_green": all(control["acceptance"].values()),
        "identity_target_mix_preserved": identity_state["weights"] == DEFAULT_WEIGHTS,
        "secondary_target_count": len(secondary_targets) == 12,
        "secondary_targets_all_active": all(len(target.deltas) > 0 for target in secondary_targets.values()),
        "secondary_displacement_bounded": 0.0 < displacement["max_distance_mm"] < 4.0,
        "secondary_moves_real_geometry": displacement["moved_vertices"] > 100,
        "topology_preserved": len(identity_variant.vertices) == len(secondary_raw.vertices) and identity_variant.faces == secondary_raw.faces,
        "head_uv_preserved": head_uv_report["status"] == "pass",
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
            "shared_skin_map_hashes": control_textures,
        },
        "ab_variable": "secondary_facial_geometry_only",
        "coordinate_conversion": control["coordinate_conversion"],
        "identity_target_mix": identity_state,
        "landmarks": landmark_packet(landmarks),
        "secondary_forms": {
            "schema": "axm.game-assets.hm08-secondary-forms.v0.1",
            "target_rows": {name: len(target.deltas) for name, target in sorted(secondary_targets.items())},
            "target_state": secondary_state,
            "displacement": displacement,
        },
        "delivery": delivery,
        "acceptance": acceptance,
        "truth": {
            "high_end_anatomy_claim": False,
            "aesthetic_improvement_claim": False,
            "notes": [
                "Candidate changes only low-amplitude AXM-native secondary facial geometry relative to the generic-skin+eyes control.",
                "Promotion requires real Godot A/B inspection; deterministic displacement alone is not an aesthetic score.",
                "Targets remain reversible sparse source state rather than destructive mesh edits."
            ],
        },
    }
    payload = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8")
    (root / "face-secondary-package.json").write_bytes(payload)
    manifest["manifest_sha256"] = _sha(payload)
    if not all(acceptance.values()):
        raise ValueError(f"secondary face package acceptance failed: {acceptance}")
    return manifest


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("output", nargs="?", default="build/hm08-face-secondary")
    parser.add_argument("--texture-size", type=int, default=128)
    args = parser.parse_args()
    result = build_face_secondary_package(args.output, texture_size=args.texture_size)
    print(json.dumps({"acceptance":result["acceptance"],"secondary_forms":result["secondary_forms"],"delivery":result["delivery"]}, indent=2))
