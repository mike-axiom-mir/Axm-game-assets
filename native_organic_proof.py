#!/usr/bin/env python3
"""AXM native reconstructable organic-detail proof v0.1."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from native_geometry import Mesh, make_uv_sphere, scale, topology_report, triangulate
from native_parametric import build_variant, rebuild_variant, topology_digest
from native_preview import write_preview
from native_surface import displacement_stats, gaussian_mask, normal_displace, smooth, subdivide, validate_multires
from native_target_authoring import author_normal_target, author_offset_target, box_region, gaussian_region

SCHEMA = "axm.game-assets.native-organic-proof.v0.1"


def _sha256(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def make_head_seed() -> Mesh:
    return scale(make_uv_sphere(1.0, segments=16, rings=8, name="sentinel_head_seed"), (0.16, 0.22, 0.18))


def build_target_library(seed: Mesh):
    nose = author_normal_target(
        seed,
        "nose_bridge_forward",
        0.035,
        region=gaussian_region((0.0, -0.005, 0.17), (0.050, 0.070, 0.055)),
        threshold=1e-5,
    )
    brow = author_normal_target(
        seed,
        "brow_ridge",
        0.014,
        region=gaussian_region((0.0, 0.070, 0.155), (0.105, 0.045, 0.055)),
        threshold=1e-5,
    )
    cheek = author_offset_target(
        seed,
        "injured_left_cheek",
        (0.006, -0.004, 0.008),
        region=box_region((-0.145, -0.065, 0.070), (-0.018, 0.040, 0.180), feather=0.035),
        threshold=1e-5,
    )
    jaw = author_offset_target(
        seed,
        "jaw_heavier",
        (0.0, -0.012, 0.006),
        region=gaussian_region((0.0, -0.145, 0.075), (0.135, 0.065, 0.095)),
        threshold=1e-5,
    )
    return {target.name: target for target in (nose, brow, cheek, jaw)}


def _view(preview: dict[str, object], view: str):
    return next(item for item in preview["views"] if item["view"] == view)


def build_organic_proof(output: str | Path, *, preview_size: int = 96, micro_seed: int = 4401) -> dict[str, object]:
    root = Path(output)
    root.mkdir(parents=True, exist_ok=True)
    seed = make_head_seed()
    targets = build_target_library(seed)
    weights = {
        "nose_bridge_forward": 0.90,
        "brow_ridge": 0.65,
        "injured_left_cheek": 0.55,
        "jaw_heavier": 0.35,
    }
    variant = build_variant(
        seed,
        targets,
        weights,
        seed_id="axm-sentinel-head-fixture-v1",
        seed_source="AXM native procedural fixture",
        seed_license="AXM code",
        unit_meters=1.0,
        name="sentinel_head_variant",
    )
    rebuilt = rebuild_variant(seed, targets, variant.state)
    reconstruction_exact = rebuilt.mesh.vertices == variant.mesh.vertices and rebuilt.mesh.faces == variant.mesh.faces

    detailed = subdivide(variant.mesh, 2, name="sentinel_head_detail")
    detailed = smooth(detailed, iterations=1, strength=0.08)
    skin_region = gaussian_mask((0.0, 0.015, 0.10), 0.25)
    micro = normal_displace(detailed, 0.0012, seed=micro_seed, mask=skin_region, name="sentinel_head_micro")
    micro_stats = displacement_stats(detailed, micro)
    multires = validate_multires(variant.mesh, micro)

    seed_preview = write_preview(seed, root / "preview-seed", size=preview_size)
    variant_preview = write_preview(variant.mesh, root / "preview-variant", size=preview_size)
    detail_preview = write_preview(micro, root / "preview-detail", size=preview_size)

    seed_front = _view(seed_preview, "front")
    variant_front = _view(variant_preview, "front")
    seed_side = _view(seed_preview, "side")
    variant_side = _view(variant_preview, "side")
    detail_side = _view(detail_preview, "side")

    manifest: dict[str, object] = {
        "schema": SCHEMA,
        "asset": "sentinel-head-organic-fixture",
        "seed": {
            "vertices": len(seed.vertices),
            "triangles": len(triangulate(seed).faces),
            "topology_digest": topology_digest(seed),
            "topology": topology_report(seed),
        },
        "targets": [{
            "name": name,
            "weight": weights[name],
            "rows": len(targets[name].deltas),
        } for name in sorted(targets)],
        "parametric_state": variant.state,
        "detail": {
            "vertices": len(micro.vertices),
            "triangles": len(triangulate(micro).faces),
            "multires": multires,
            "micro_displacement": micro_stats,
        },
        "previews": {
            "seed": seed_preview,
            "variant": variant_preview,
            "detail": detail_preview,
        },
        "acceptance": {
            "reconstruction_exact": reconstruction_exact,
            "parametric_topology_preserved": topology_digest(seed) == topology_digest(variant.mesh),
            "detail_triangle_growth": len(triangulate(micro).faces) > len(triangulate(variant.mesh).faces),
            "multires_structural_valid": multires["status"] == "pass",
            "front_depth_changed_by_targets": seed_front["hashes"]["depth"] != variant_front["hashes"]["depth"],
            "side_silhouette_changed_by_targets": seed_side["hashes"]["silhouette"] != variant_side["hashes"]["silhouette"],
            "detail_normal_signal_changed": variant_side["hashes"]["normal"] != detail_side["hashes"]["normal"],
        },
        "truth": {
            "high_end_face_claim": False,
            "anatomy_claim": "fixture only",
            "notes": [
                "This proves fixed-topology identity edits + reconstructable target weights + later multires detail, not anatomical realism.",
                "Target edits happen before topology-changing subdivision.",
                "Diagnostic hash changes prove selected visual signals changed, not that the change is aesthetically better.",
                "The next high-value step is applying the same machinery to a suitable CC0 human seed topology and curating anatomically meaningful targets."
            ],
        },
    }
    manifest_bytes = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8")
    (root / "organic-proof.json").write_bytes(manifest_bytes)
    manifest["manifest_sha256"] = _sha256(manifest_bytes)
    return manifest
