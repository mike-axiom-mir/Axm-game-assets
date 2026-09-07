#!/usr/bin/env python3
"""Receipt-bearing native rigid-asset manufacturing route."""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from native_geometry import aabb_collision, topology_report
from native_gltf import write_gltf
from native_pbr import PaintedMetalSpec, write_painted_metal
from native_uv import box_project, read_obj_uv, spherical_project, validate_uv

SCHEMA = "axm.game-assets.native-rigid-package.v0.1"


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _sha256_bytes(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _receipt(stage: str, status: str, tool: str, evidence: dict[str, Any], notes: list[str] | None = None) -> dict[str, Any]:
    payload = {
        "stage": stage,
        "status": status,
        "tool": tool,
        "created_at": _now(),
        "evidence": evidence,
        "notes": notes or [],
    }
    payload["receipt_sha256"] = _sha256_bytes(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode())
    return payload


def _choose_uv(mesh, imported_uv, mode: str):
    imported_report = validate_uv(mesh, imported_uv)
    if mode == "preserve":
        if imported_report["status"] != "pass":
            raise ValueError(f"preserve requested but source UV is invalid: {imported_report}")
        return imported_uv, "preserved"
    if mode == "box":
        return box_project(mesh), "box_projection"
    if mode == "spherical":
        return spherical_project(mesh), "spherical_projection"
    if mode != "auto":
        raise ValueError(f"unknown UV mode {mode}")
    if imported_report["status"] == "pass" and imported_uv.uvs:
        return imported_uv, "preserved"
    return box_project(mesh), "box_projection_fallback"


def build_rigid_package(input_obj: str | Path, output: str | Path, *, uv_mode: str = "auto", material_size: int = 512, seed: int = 1, spec: PaintedMetalSpec = PaintedMetalSpec()) -> dict[str, Any]:
    source = Path(input_obj)
    if not source.exists():
        raise FileNotFoundError(source)
    root = Path(output)
    root.mkdir(parents=True, exist_ok=True)
    receipts_dir = root / "receipts"
    receipts_dir.mkdir(exist_ok=True)
    source_dir = root / "source"
    source_dir.mkdir(exist_ok=True)
    source_copy = source_dir / source.name
    shutil.copyfile(source, source_copy)

    mesh, imported_uv = read_obj_uv(source)
    geometry = topology_report(mesh)
    if geometry["invalid_indices"] or geometry["degenerate_faces"]:
        raise ValueError(f"source geometry failed structural gate: {geometry}")
    receipts: list[dict[str, Any]] = []
    receipts.append(_receipt(
        "geometry_intake",
        "pass",
        "internal-native-geometry-v0.1",
        {"source_sha256": _sha256_file(source_copy), "topology": geometry},
        ["Boundary/non-manifold counts are recorded but are not a universal rigid-prop failure gate yet."],
    ))

    uvmap, uv_decision = _choose_uv(mesh, imported_uv, uv_mode)
    uv_report = validate_uv(mesh, uvmap)
    if uv_report["status"] != "pass":
        raise ValueError(f"UV gate failed: {uv_report}")
    receipts.append(_receipt(
        "uv",
        "pass",
        "internal-native-uv-v0.1",
        {"decision": uv_decision, "report": uv_report},
    ))

    material = write_painted_metal(root / "textures", size=material_size, seed=seed, spec=spec)
    material_evidence = {name: meta["sha256"] for name, meta in material["maps"].items()}
    receipts.append(_receipt(
        "materials",
        "pass",
        "internal-native-pbr-v0.1",
        {"seed": seed, "size": material_size, "maps": material_evidence},
        ["Procedural authored material; not a physically measured scan."],
    ))

    delivery = write_gltf(mesh, uvmap, root)
    receipts.append(_receipt(
        "engine_pack",
        "pass",
        "internal-native-gltf-v0.1",
        delivery,
        ["Rigid glTF v0.1 generates tangent frames natively but has no skeleton, morph targets, skinning, or animation."],
    ))

    collision = aabb_collision(mesh)
    collision_bytes = (json.dumps(collision, indent=2, sort_keys=True) + "\n").encode()
    (root / "collision.json").write_bytes(collision_bytes)
    receipts.append(_receipt(
        "collision",
        "pass",
        "internal-native-geometry-v0.1",
        {"collision_sha256": _sha256_bytes(collision_bytes), "collision": collision},
        ["AABB only; convex decomposition and semantic collision remain future capability."],
    ))

    for index, item in enumerate(receipts):
        (receipts_dir / f"{index:03d}-{item['stage']}.json").write_text(json.dumps(item, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    delivery_files: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.name == "package-manifest.json" or "receipts" in path.parts:
            continue
        delivery_files[path.relative_to(root).as_posix()] = _sha256_file(path)

    manifest = {
        "schema": SCHEMA,
        "created_at": _now(),
        "asset": {"name": mesh.name, "source": source_copy.relative_to(root).as_posix()},
        "native_route": [
            "internal-native-geometry-v0.1",
            "internal-native-uv-v0.1",
            "internal-native-pbr-v0.1",
            "internal-native-gltf-v0.1",
        ],
        "geometry": geometry,
        "uv": {"decision": uv_decision, "report": uv_report},
        "collision": collision,
        "delivery": delivery,
        "files": delivery_files,
        "receipts": [item["receipt_sha256"] for item in receipts],
        "truth": {
            "status": "prototype_rigid_route",
            "blender_required": False,
            "high_end_character_claim": False,
            "known_limits": [
                "Rigid meshes only",
                "No skeletal or morph state",
                "Fallback UV projection is not a production atlas optimizer",
                "AABB collision only",
                "No in-engine screenshot/performance receipt yet"
            ]
        }
    }
    manifest_bytes = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode()
    (root / "package-manifest.json").write_bytes(manifest_bytes)
    manifest["manifest_sha256"] = _sha256_bytes(manifest_bytes)
    return manifest


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="AXM native rigid asset package route")
    p.add_argument("input_obj")
    p.add_argument("output")
    p.add_argument("--uv", choices=("auto", "preserve", "box", "spherical"), default="auto")
    p.add_argument("--material-size", type=int, default=512)
    p.add_argument("--seed", type=int, default=1)
    return p


if __name__ == "__main__":
    args = parser().parse_args()
    result = build_rigid_package(args.input_obj, args.output, uv_mode=args.uv, material_size=args.material_size, seed=args.seed)
    print(json.dumps({"manifest_sha256": result["manifest_sha256"], "delivery": result["delivery"], "truth": result["truth"]}, indent=2))
