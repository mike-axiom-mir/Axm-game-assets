#!/usr/bin/env python3
"""Export the hm08 neutral face + reversible motion targets to native glTF.

This delivery is intentionally a motion-observer package: one source-grounded
head surface, the existing physical skin maps, seven morph channels and three
weight-animation clips. Eyes, hair and the full humanoid skeleton remain in the
accepted current/full-body packages and are not duplicated here.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

from native_facial_gltf import compile_facial_character_gltf
from native_geometry import scale, vertex_normals
from native_gltf import _sha256, validate_gltf
from native_hm08_face_eyes import RAW_TO_M, SEED_ROOT
from native_hm08_face_motion import TARGET_ORDER, build_hm08_face_motion_state
from native_hm08_skin_physical import write_hm08_physical_skin
from native_morph import apply_morphs
from native_skin import Joint, Skeleton, SkinWeights
from native_skin_material import SkinMaterialSpec
from native_uv import read_obj_uv, validate_uv

SCHEMA = "axm.game-assets.hm08-face-motion-gltf.v0.1"
ASSET_NAME = "sentinel_hm08_face_motion_v0_1"


def _head_only_skin(vertex_count: int) -> tuple[Skeleton, SkinWeights]:
    skeleton = Skeleton([Joint("head_root")])
    weights = SkinWeights(
        joints=[(0, 0, 0, 0)] * vertex_count,
        weights=[(1.0, 0.0, 0.0, 0.0)] * vertex_count,
    )
    return skeleton, weights


def _add_deformation_normals(neutral_m, morphs_m) -> dict[str, float]:
    """Attach deterministic full-weight normal deltas to each position morph.

    The source targets remain pure geometry deltas. Delivery normals are derived
    from the same neutral topology after applying each target at weight 1.0.
    The native character compiler then derives tangent deltas in expanded UV
    corner space from these positions + normals.
    """
    base_normals = vertex_normals(neutral_m)
    maxima: dict[str, float] = {}
    for morph in morphs_m:
        deformed = apply_morphs(neutral_m, [morph], [1.0], name=f"{morph.name}_normal_probe")
        deformed_normals = vertex_normals(deformed)
        deltas = [
            (
                deformed_normal[0] - base_normal[0],
                deformed_normal[1] - base_normal[1],
                deformed_normal[2] - base_normal[2],
            )
            for base_normal, deformed_normal in zip(base_normals, deformed_normals)
        ]
        morph.normal_deltas = deltas
        maxima[morph.name] = max(
            math.sqrt(delta[0] * delta[0] + delta[1] * delta[1] + delta[2] * delta[2])
            for delta in deltas
        )
    return maxima


def write_hm08_face_motion_gltf(
    output: str | Path,
    *,
    texture_size: int = 128,
    skin_seed: int = 20801,
) -> dict[str, object]:
    root = Path(output)
    root.mkdir(parents=True, exist_ok=True)

    neutral_raw, _targets, morphs_m, clips, motion = build_hm08_face_motion_state()
    _seed_mesh, uvmap = read_obj_uv(SEED_ROOT / "head.obj", name="hm08_head_v0_2")
    uv_report = validate_uv(neutral_raw, uvmap)
    if uv_report["status"] != "pass":
        raise ValueError(f"neutral hm08 UV state invalid: {uv_report}")

    neutral_m = scale(neutral_raw, RAW_TO_M, name=ASSET_NAME)
    normal_delta_maxima = _add_deformation_normals(neutral_m, morphs_m)
    skeleton, skin_weights = _head_only_skin(len(neutral_m.vertices))

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
    skin = write_hm08_physical_skin(
        root / "textures",
        mesh=neutral_raw,
        uvmap=uvmap,
        size=texture_size,
        seed=skin_seed,
        spec=skin_spec,
    )

    binary_name = f"{ASSET_NAME}.bin"
    gltf_name = f"{ASSET_NAME}.gltf"
    document, binary = compile_facial_character_gltf(
        neutral_m,
        uvmap,
        skeleton,
        skin_weights,
        morphs_m,
        morph_animations=clips,
        buffer_uri=binary_name,
        base_color_uri="textures/base_color.png",
        normal_uri="textures/normal.png",
        orm_uri="textures/orm.png",
    )

    # The generic character compiler is material-agnostic. This package is a
    # human skin observer, so explicitly keep the material non-metallic.
    material = document["materials"][0]
    material["name"] = "AXM_Sentinel_Skin_Physical_v0_1_MotionObserver"
    material["pbrMetallicRoughness"]["metallicFactor"] = 0.0
    material["pbrMetallicRoughness"]["roughnessFactor"] = 1.0

    target_names = document["meshes"][0].get("extras", {}).get("targetNames", [])
    primitive_targets = document["meshes"][0]["primitives"][0].get("targets", [])
    compiler_axm = document.get("extras", {}).get("axm", {})
    weight_animations = [
        animation
        for animation in document.get("animations", [])
        if any(channel.get("target", {}).get("path") == "weights" for channel in animation.get("channels", []))
    ]
    acceptance = {
        "motion_source_green": motion["status"] == "pass",
        "neutral_uv_preserved": uv_report["status"] == "pass",
        "explicit_meter_delivery": RAW_TO_M == 0.1,
        "seven_named_morph_targets": target_names == list(TARGET_ORDER),
        "morph_normal_deltas_present": (
            len(primitive_targets) == len(TARGET_ORDER)
            and all("NORMAL" in entry for entry in primitive_targets)
            and all(morph.normal_deltas is not None and len(morph.normal_deltas) == len(neutral_m.vertices) for morph in morphs_m)
        ),
        "morph_tangent_deltas_present": (
            len(primitive_targets) == len(TARGET_ORDER)
            and all("TANGENT" in entry for entry in primitive_targets)
            and int(compiler_axm.get("morph_tangent_targets", -1)) == len(TARGET_ORDER)
        ),
        "three_weight_animations": len(weight_animations) == 3,
        "skin_nonmetal": material["pbrMetallicRoughness"]["metallicFactor"] == 0.0,
        "physical_skin_maps_present": all(
            (root / "textures" / f"{name}.png").exists()
            for name in ("base_color", "normal", "orm")
        ),
    }

    axm = document.setdefault("extras", {}).setdefault("axm", {})
    axm.update({
        "schema": SCHEMA,
        "motion_target_order": list(TARGET_ORDER),
        "motion_clips": [clip.name for clip in clips],
        "neutral_identity_sha256": motion["neutral"]["sha256"],
        "deformation_normal_delta_max": normal_delta_maxima,
        "truth": (
            "Real hm08 neutral geometry with reversible meter-space morph targets, derived deformation-normal deltas, compiler-derived expanded UV-corner tangent deltas, and morph-weight animation channels. "
            "This package is an engine motion observer, not final facial acting or full current-face assembly."
        ),
    })

    if not all(acceptance.values()):
        raise ValueError(f"hm08 face-motion glTF preflight failed: {acceptance}")

    (root / binary_name).write_bytes(binary)
    gltf_bytes = (json.dumps(document, indent=2, sort_keys=True) + "\n").encode("utf-8")
    (root / gltf_name).write_bytes(gltf_bytes)
    validation = validate_gltf(document, binary, root)
    if validation["status"] != "pass":
        raise ValueError(f"hm08 face-motion glTF validation failed: {validation}")

    acceptance["gltf_structural_valid"] = True
    manifest: dict[str, object] = {
        "schema": SCHEMA,
        "asset": ASSET_NAME,
        "gltf": gltf_name,
        "binary": binary_name,
        "gltf_sha256": _sha256(gltf_bytes),
        "binary_sha256": _sha256(binary),
        "vertices": len(neutral_m.vertices),
        "faces": len(neutral_m.faces),
        "triangles": document["extras"]["axm"]["triangles"],
        "morph_targets": target_names,
        "morph_tangent_targets": int(document["extras"]["axm"]["morph_tangent_targets"]),
        "motion_clips": [animation["name"] for animation in weight_animations],
        "deformation_normal_delta_max": normal_delta_maxima,
        "skin": skin,
        "motion": motion,
        "validation": validation,
        "acceptance": acceptance,
        "truth": {
            "full_current_face_assembly": False,
            "engine_motion_observer": True,
            "visual_quality_claim": False,
            "notes": [
                "The neutral head is the same accepted hm08 identity substrate, converted explicitly from source decimeters to meters.",
                "Morph normal deltas are deterministically derived from each full-weight deformed source topology.",
                "The character compiler derives VEC3 morph tangent deltas from deformed positions/normals in expanded UV-corner space so normal-mapped deformation preserves seam-specific tangent bases.",
                "A one-joint head skin exists only to satisfy the native skinned-character glTF path; facial motion itself is morph-driven.",
                "Eyes, brows, lashes, hair and full humanoid deformation remain separate accepted/active packages and are not silently replaced here.",
            ],
        },
    }
    manifest_bytes = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8")
    (root / "hm08-face-motion-gltf.json").write_bytes(manifest_bytes)
    manifest["manifest_sha256"] = _sha256(manifest_bytes)
    return manifest


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("output", nargs="?", default="build/hm08-face-motion-gltf")
    parser.add_argument("--texture-size", type=int, default=128)
    args = parser.parse_args()
    result = write_hm08_face_motion_gltf(args.output, texture_size=args.texture_size)
    print(json.dumps({
        "asset": result["asset"],
        "gltf_sha256": result["gltf_sha256"],
        "morph_targets": result["morph_targets"],
        "morph_tangent_targets": result["morph_tangent_targets"],
        "motion_clips": result["motion_clips"],
        "acceptance": result["acceptance"],
    }, indent=2, sort_keys=True))
