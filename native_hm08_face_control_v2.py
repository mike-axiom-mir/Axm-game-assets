#!/usr/bin/env python3
"""Clean head+skin control for the hm08 face/eyes A/B.

Run 2's first head-only Godot control used raw MakeHuman decimeter geometry and
the generic rigid compiler's metallic default. That made it an invalid visual
control for the later correctly scaled/non-metal face+eyes package.

This v0.2 control fixes only those delivery variables: same repaired hm08 face,
same target weights, same skin recipe, explicit dm->m conversion, metallic 0,
no eyes. It exists to make the eye A/B comparable.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from native_geometry import scale
from native_hm08_face_proof import DEFAULT_WEIGHTS
from native_multi_gltf import MaterialPrimitive, write_multi_gltf
from native_skin_material import SkinMaterialSpec, write_skin_material
from native_targets import load_target, mix_targets
from native_uv import read_obj_uv, validate_uv

SCHEMA = "axm.game-assets.hm08-face-control.v0.2"
SEED_ROOT = Path("seed_data/hm08_head_v0.2")
RAW_TO_M = 0.1


def _sha(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def build_face_control_v2(output: str | Path, *, texture_size: int = 128, seed: int = 20801) -> dict[str, object]:
    root = Path(output)
    root.mkdir(parents=True, exist_ok=True)
    seed_manifest = json.loads((SEED_ROOT / "seed-manifest.json").read_text(encoding="utf-8"))
    raw_head, uvmap = read_obj_uv(SEED_ROOT / "head.obj", name="hm08_head_v0_2")
    library = {
        name: load_target(SEED_ROOT / "targets" / f"{name}.target", license="CC0-source-remap")
        for name in sorted(DEFAULT_WEIGHTS)
    }
    raw_variant, target_state = mix_targets(raw_head, library, DEFAULT_WEIGHTS, name="sentinel_hm08_face_control_v0_2")
    head_m = scale(raw_variant, RAW_TO_M, name="sentinel_hm08_face_control_v0_2")
    uv_report = validate_uv(head_m, uvmap)
    if uv_report["status"] != "pass":
        raise ValueError(f"meter-scaled face control broke UV state: {uv_report}")

    skin_spec = SkinMaterialSpec(
        base_rgb=(166, 119, 101), undertone_rgb=(142, 72, 67),
        roughness=0.50, oiliness=0.15, pore_strength=0.38,
        freckle_density=0.020, subsurface_weight_hint=0.56,
        specular_ior_hint=1.40,
    )
    skin = write_skin_material(root / "textures" / "skin", size=texture_size, seed=seed, spec=skin_spec)
    delivery = write_multi_gltf([
        MaterialPrimitive(
            head_m, uvmap, "AXM_Sentinel_Skin_Prototype",
            "textures/skin/base_color.png",
            "textures/skin/normal.png",
            "textures/skin/orm.png",
            metallic_factor=0.0,
        )
    ], root, name="sentinel_hm08_face_control_v0_2")

    acceptance = {
        "repaired_seed_used": seed_manifest["basemesh_id"] == "axm-hm08-head-v0.2",
        "explicit_dm_to_m": RAW_TO_M == 0.1,
        "uv_preserved": uv_report["status"] == "pass",
        "one_skin_primitive": delivery["primitive_count"] == 1 and delivery["material_count"] == 1,
        "gltf_structural_valid": delivery["validation"]["status"] == "pass",
    }
    manifest: dict[str, object] = {
        "schema": SCHEMA,
        "asset": "sentinel_hm08_face_control_v0_2",
        "seed_basemesh": seed_manifest["basemesh_id"],
        "coordinate_conversion": {"source_unit":"decimeter","delivery_unit":"meter","scale":RAW_TO_M},
        "target_mix": target_state,
        "skin": skin,
        "delivery": delivery,
        "acceptance": acceptance,
        "truth": {
            "high_end_face_claim": False,
            "control_only": True,
            "supersedes_visual_control": "sentinel_hm08_face_candidate_v0_1",
            "repair_reason": "Old control differed from face+eyes in unit scale and metallic material semantics; v0.2 isolates eye presence as the intended A/B variable."
        }
    }
    payload = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8")
    (root / "face-control-v2.json").write_bytes(payload)
    manifest["manifest_sha256"] = _sha(payload)
    if not all(acceptance.values()):
        raise ValueError(f"face control v0.2 failed: {acceptance}")
    return manifest


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(); p.add_argument("output", nargs="?", default="build/hm08-face-control-v2"); p.add_argument("--texture-size", type=int, default=128)
    args = p.parse_args(); result = build_face_control_v2(args.output, texture_size=args.texture_size)
    print(json.dumps({"acceptance":result["acceptance"],"delivery":result["delivery"]}, indent=2))
