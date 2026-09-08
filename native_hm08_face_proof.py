#!/usr/bin/env python3
"""First real-human Sentinel face candidate proof on repaired hm08 v0.2.

This is a fidelity bridge from the genesis procedural head-like fixture to real
fixed human topology. It preserves hm08 UV state, applies deterministic sparse
face targets, authors a deterministic skin material, emits a glTF snapshot and
records diagnostic visual signal changes. It is not a high-end face claim.
"""
from __future__ import annotations

import hashlib
import json
from math import sqrt
from pathlib import Path
from typing import Mapping

from native_gltf import write_gltf
from native_preview import write_preview
from native_skin_material import SkinMaterialSpec, write_skin_material
from native_targets import load_target, mix_targets
from native_uv import read_obj_uv, validate_uv, write_obj_uv

SCHEMA = "axm.game-assets.hm08-face-proof.v0.1"
SEED_ROOT = Path("seed_data/hm08_head_v0.2")
DEFAULT_WEIGHTS = {
    "nose-width1-incr": 0.35,
    "l-cheek-bones-incr": 0.22,
    "r-cheek-bones-incr": 0.22,
}


def _sha(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _preview_view(preview: dict[str, object], name: str) -> dict[str, object]:
    return next(view for view in preview["views"] if view["view"] == name)  # type: ignore[index,return-value]


def _displacement(base_vertices, variant_vertices) -> dict[str, float | int]:
    distances = [
        sqrt(sum((after[axis] - before[axis]) ** 2 for axis in range(3)))
        for before, after in zip(base_vertices, variant_vertices)
    ]
    moved = [distance for distance in distances if distance > 1e-15]
    return {
        "moved_vertices": len(moved),
        "mean_moved_distance": sum(moved) / len(moved) if moved else 0.0,
        "max_distance": max(moved, default=0.0),
    }


def build_hm08_face_proof(
    output: str | Path,
    *,
    weights: Mapping[str, float] = DEFAULT_WEIGHTS,
    texture_size: int = 128,
    preview_size: int = 160,
    seed: int = 20801,
) -> dict[str, object]:
    root = Path(output)
    root.mkdir(parents=True, exist_ok=True)

    seed_manifest = json.loads((SEED_ROOT / "seed-manifest.json").read_text(encoding="utf-8"))
    if seed_manifest["basemesh_id"] != "axm-hm08-head-v0.2":
        raise ValueError("preferred repaired hm08 head seed v0.2 is unavailable")

    base_mesh, uvmap = read_obj_uv(SEED_ROOT / "head.obj", name="hm08_head_v0_2")
    base_uv_report = validate_uv(base_mesh, uvmap)
    if base_uv_report["status"] != "pass":
        raise ValueError(f"seed UV state invalid: {base_uv_report}")

    library = {
        target_name: load_target(SEED_ROOT / "targets" / f"{target_name}.target", license="CC0-source-remap")
        for target_name in sorted(weights)
    }
    variant, mix_state = mix_targets(
        base_mesh,
        library,
        weights,
        name="sentinel_hm08_face_candidate_v0_1",
    )
    variant_uv_report = validate_uv(variant, uvmap)
    if variant_uv_report["status"] != "pass":
        raise ValueError(f"variant no longer matches preserved UV state: {variant_uv_report}")

    displacement = _displacement(base_mesh.vertices, variant.vertices)
    if int(displacement["moved_vertices"]) <= 0:
        raise ValueError("face target mix changed no human vertices")

    source_dir = root / "source"
    source_dir.mkdir(exist_ok=True)
    write_obj_uv(base_mesh, uvmap, source_dir / "base-head.obj", material="AXM_HM08_Base")
    write_obj_uv(variant, uvmap, source_dir / "sentinel-face-candidate.obj", material="AXM_Sentinel_Skin_Prototype")

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
    skin = write_skin_material(root / "textures", size=texture_size, seed=seed, spec=skin_spec)
    delivery = write_gltf(
        variant,
        uvmap,
        root,
        material_name="AXM_Sentinel_Skin_Prototype",
    )

    base_preview = write_preview(base_mesh, root / "preview" / "base", size=preview_size, views=("front", "side", "top"))
    variant_preview = write_preview(variant, root / "preview" / "variant", size=preview_size, views=("front", "side", "top"))

    signal_changes = {}
    changed_signals = 0
    for view_name in ("front", "side", "top"):
        before = _preview_view(base_preview, view_name)
        after = _preview_view(variant_preview, view_name)
        changes = {
            signal: before["hashes"][signal] != after["hashes"][signal]  # type: ignore[index]
            for signal in ("silhouette", "depth", "normal")
        }
        changed_signals += sum(bool(value) for value in changes.values())
        signal_changes[view_name] = changes

    acceptance = {
        "preferred_repaired_human_seed_used": seed_manifest["basemesh_id"] == "axm-hm08-head-v0.2",
        "seed_uv_valid": base_uv_report["status"] == "pass",
        "variant_uv_preserved": variant_uv_report["status"] == "pass" and len(uvmap.uvs) == int(seed_manifest["extraction"]["compact_uvs"]),
        "topology_preserved": len(base_mesh.vertices) == len(variant.vertices) and base_mesh.faces == variant.faces,
        "face_targets_moved_vertices": int(displacement["moved_vertices"]) >= 100,
        "diagnostic_signal_changed": changed_signals >= 2,
        "skin_material_deterministic": skin["truth"]["deterministic"] is True,
        "gltf_structural_valid": delivery["validation"]["status"] == "pass",
        "skin_material_identity": delivery["material_name"] == "AXM_Sentinel_Skin_Prototype",
    }

    manifest: dict[str, object] = {
        "schema": SCHEMA,
        "asset": "sentinel_hm08_face_candidate_v0_1",
        "seed_basemesh": seed_manifest["basemesh_id"],
        "seed_head_sha256": seed_manifest["outputs"]["head_obj"]["sha256"],
        "weights": {name: float(weights[name]) for name in sorted(weights)},
        "target_mix": mix_state,
        "displacement": displacement,
        "uv": {"base": base_uv_report, "variant": variant_uv_report},
        "skin": skin,
        "delivery": delivery,
        "diagnostic_signal_changes": signal_changes,
        "acceptance": acceptance,
        "truth": {
            "human_topology": True,
            "high_end_face_claim": False,
            "identity_quality_claim": False,
            "notes": [
                "This proof establishes reconstructable face variation on repaired fixed human topology.",
                "Sparse target weights are authored experiment state, not an aesthetic ranking or demographic identity claim.",
                "The procedural skin maps are not semantic face scans and still lack region-aware pores/wrinkles.",
                "Eyes, lashes, tearline, hair, facial rigging and real engine close-up judgment remain separate later gates.",
                "Diagnostic hash changes prove that selected visual signals changed, not that the variant is automatically better."
            ],
        },
    }
    manifest_bytes = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8")
    (root / "hm08-face-proof.json").write_bytes(manifest_bytes)
    manifest["manifest_sha256"] = _sha(manifest_bytes)
    if not all(acceptance.values()):
        raise ValueError(f"hm08 face proof acceptance failed: {acceptance}")
    return manifest


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("output", nargs="?", default="build/hm08-face-proof")
    parser.add_argument("--texture-size", type=int, default=128)
    parser.add_argument("--preview-size", type=int, default=160)
    parser.add_argument("--seed", type=int, default=20801)
    args = parser.parse_args()
    proof = build_hm08_face_proof(args.output, texture_size=args.texture_size, preview_size=args.preview_size, seed=args.seed)
    print(json.dumps({"acceptance": proof["acceptance"], "displacement": proof["displacement"], "delivery": proof["delivery"]}, indent=2))
