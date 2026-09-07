#!/usr/bin/env python3
"""AXM native short-hair proof package v0.1."""
from __future__ import annotations

import hashlib
import json
from math import sqrt
from pathlib import Path

from native_geometry import bounds, combine
from native_hair import generate_short_hair, hair_cards_with_uv, validate_hair
from native_hair_gltf import write_hair_gltf
from native_hair_material import write_hair_material
from native_organic_proof import make_head_seed
from native_preview import write_preview
from native_uv import validate_uv

SCHEMA = "axm.game-assets.native-hair-proof.v0.1"


def _sha(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _distance(a, b) -> float:
    return sqrt(sum((a[axis] - b[axis]) ** 2 for axis in range(3)))


def _scalp_candidates(head):
    lo, hi = bounds(head)
    span_y = max(hi[1] - lo[1], 1e-9)
    span_z = max(hi[2] - lo[2], 1e-9)
    return [
        point for point in head.vertices
        if point[1] >= lo[1] + span_y * 0.48 and point[2] >= lo[2] + span_z * 0.18
    ]


def _view(preview, name):
    return next(item for item in preview["views"] if item["view"] == name)


def build_hair_proof(output: str | Path, *, guide_count: int = 64, segments: int = 6, seed: int = 731, texture_size: int = 64, preview_size: int = 96) -> dict[str, object]:
    root = Path(output)
    root.mkdir(parents=True, exist_ok=True)
    head = make_head_seed()
    system = generate_short_hair(head, guide_count=guide_count, segments=segments, seed=seed)
    hair_report = validate_hair(system)
    if hair_report["status"] != "pass":
        raise ValueError(f"hair state failed: {hair_report}")
    cards, uvmap = hair_cards_with_uv(system, name="sentinel_short_hair")
    uv_report = validate_uv(cards, uvmap)
    if uv_report["status"] != "pass":
        raise ValueError(f"hair card UV failed: {uv_report}")

    material = write_hair_material(root / "textures", size=texture_size, seed=seed)
    delivery = write_hair_gltf(cards, uvmap, root, alpha_cutoff=material["renderer_hints"]["alpha_cutoff"])

    roots = [guide.points[0] for guide in system.guides]
    scalp = _scalp_candidates(head)
    root_to_head = [min(_distance(root_point, point) for point in head.vertices) for root_point in roots]
    scalp_to_root = [min(_distance(point, root_point) for root_point in roots) for point in scalp]
    coverage = {
        "scalp_samples": len(scalp),
        "mean_scalp_to_root": sum(scalp_to_root) / len(scalp_to_root) if scalp_to_root else 0.0,
        "max_scalp_to_root": max(scalp_to_root, default=0.0),
        "mean_root_to_head": sum(root_to_head) / len(root_to_head) if root_to_head else 0.0,
        "max_root_to_head": max(root_to_head, default=0.0),
    }

    bare_preview = write_preview(head, root / "preview-bare", size=preview_size)
    combined = combine([head, cards], name="head_with_hair_cards")
    hair_preview = write_preview(combined, root / "preview-hair", size=preview_size)
    bare_front = _view(bare_preview, "front")
    hair_front = _view(hair_preview, "front")
    bare_side = _view(bare_preview, "side")
    hair_side = _view(hair_preview, "side")

    manifest: dict[str, object] = {
        "schema": SCHEMA,
        "asset": "sentinel-short-hair-fixture",
        "hair": hair_report,
        "uv": uv_report,
        "coverage": coverage,
        "material": material,
        "delivery": delivery,
        "preview": {"bare": bare_preview, "hair": hair_preview},
        "acceptance": {
            "hair_state_valid": hair_report["status"] == "pass",
            "strand_uv_valid": uv_report["status"] == "pass",
            "root_offset_near_scalp": coverage["max_root_to_head"] < 0.003,
            "scalp_coverage_fixture": coverage["max_scalp_to_root"] < 0.09,
            "front_geometry_signal_changed": bare_front["hashes"]["silhouette"] != hair_front["hashes"]["silhouette"],
            "side_geometry_signal_changed": bare_side["hashes"]["silhouette"] != hair_side["hashes"]["silhouette"],
            "gltf_structural_valid": delivery["validation"]["status"] == "pass",
            "alpha_card_delivery": delivery["alpha_mode"] == "MASK" and delivery["double_sided"] is True,
        },
        "truth": {
            "high_end_groom_claim": False,
            "notes": [
                "Diagnostic preview renders card geometry as opaque, so it evaluates placement/silhouette only, not alpha compositing quality.",
                "Scalp coverage is a geometric root-spacing fixture metric, not an aesthetic hair-density judgment.",
                "Production proof still requires alpha sorting, anisotropic response, scalp masking, hairline semantics and motion in a target engine.",
            ],
        },
    }
    payload = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8")
    (root / "hair-proof.json").write_bytes(payload)
    manifest["manifest_sha256"] = _sha(payload)
    return manifest
