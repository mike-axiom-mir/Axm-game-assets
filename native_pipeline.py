#!/usr/bin/env python3
"""Receipt-bearing native rigid-asset manufacturing route."""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any

from native_geometry import aabb_collision, topology_report
from native_gltf import write_gltf
from native_pbr import PaintedMetalSpec, write_painted_metal
from native_uv import box_project, read_obj_uv, spherical_project, validate_uv

SCHEMA = "axm.game-assets.native-rigid-package.v0.1"


class PackageVerificationError(ValueError):
    """Raised when a rigid package differs from its caller-pinned evidence."""


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _sha256_bytes(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _strict_json(data: bytes, *, source: str) -> dict[str, Any]:
    def reject_duplicate_keys(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise PackageVerificationError(f"{source} contains duplicate key {key!r}")
            value[key] = item
        return value

    try:
        value = json.loads(data, object_pairs_hook=reject_duplicate_keys)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PackageVerificationError(f"{source} is not valid UTF-8 JSON") from exc
    if not isinstance(value, dict):
        raise PackageVerificationError(f"{source} must contain one JSON object")
    return value


def _package_path(root: Path, relative: str, *, kind: str) -> Path:
    if not isinstance(relative, str) or not relative or "\\" in relative:
        raise PackageVerificationError(f"invalid {kind} path {relative!r}")
    raw_parts = relative.split("/")
    parsed = PurePosixPath(relative)
    if (
        parsed.is_absolute()
        or any(part in {"", ".", ".."} for part in raw_parts)
        or parsed.as_posix() != relative
    ):
        raise PackageVerificationError(f"unsafe {kind} path {relative!r}")
    return root.joinpath(*parsed.parts)


def verify_rigid_package(
    package: str | Path,
    *,
    expected_manifest_sha256: str,
) -> dict[str, Any]:
    """Verify a rigid package against a digest supplied outside that package."""
    if not isinstance(expected_manifest_sha256, str) or not expected_manifest_sha256.startswith("sha256:"):
        raise PackageVerificationError("expected_manifest_sha256 must be a caller-owned sha256 receipt")

    supplied_root = Path(package)
    if supplied_root.is_symlink() or not supplied_root.is_dir():
        raise PackageVerificationError("package root must be a real directory, not a symlink")
    root = supplied_root.resolve()
    manifest_path = root / "package-manifest.json"
    if manifest_path.is_symlink() or not manifest_path.is_file():
        raise PackageVerificationError("package-manifest.json must be a regular file")

    actual_files: set[str] = set()
    for path in root.rglob("*"):
        relative = path.relative_to(root).as_posix()
        if path.is_symlink():
            raise PackageVerificationError(f"package contains symlink {relative!r}")
        if path.is_file():
            actual_files.add(relative)
        elif not path.is_dir():
            raise PackageVerificationError(f"package contains non-regular entry {relative!r}")

    manifest_bytes = manifest_path.read_bytes()
    actual_manifest_sha256 = _sha256_bytes(manifest_bytes)
    if actual_manifest_sha256 != expected_manifest_sha256:
        raise PackageVerificationError("package manifest differs from caller-owned digest")
    manifest = _strict_json(manifest_bytes, source="package-manifest.json")
    if manifest.get("schema") != SCHEMA:
        raise PackageVerificationError(f"unsupported package schema {manifest.get('schema')!r}")

    files = manifest.get("files")
    receipt_files = manifest.get("receipt_files")
    receipt_sequence = manifest.get("receipts")
    if not isinstance(files, dict) or not isinstance(receipt_files, dict) or not isinstance(receipt_sequence, list):
        raise PackageVerificationError("manifest file and receipt inventories are required")

    expected_paths = {"package-manifest.json"}
    verified_delivery: list[tuple[str, Path, str]] = []
    for relative, expected_sha256 in files.items():
        if relative == "package-manifest.json" or relative.startswith("receipts/"):
            raise PackageVerificationError("delivery inventory cannot claim receipt paths")
        path = _package_path(root, relative, kind="delivery")
        if not isinstance(expected_sha256, str):
            raise PackageVerificationError(f"delivery digest is invalid for {relative!r}")
        expected_paths.add(relative)
        verified_delivery.append((relative, path, expected_sha256))

    verified_receipts: list[tuple[str, Path, str]] = []
    for relative in sorted(receipt_files):
        if not relative.startswith("receipts/"):
            raise PackageVerificationError(f"receipt path is outside receipts/: {relative!r}")
        path = _package_path(root, relative, kind="receipt")
        expected = receipt_files[relative]
        if not isinstance(expected, str):
            raise PackageVerificationError(f"receipt digest is invalid for {relative!r}")
        expected_paths.add(relative)
        verified_receipts.append((relative, path, expected))

    if actual_files != expected_paths:
        missing = sorted(expected_paths - actual_files)
        undeclared = sorted(actual_files - expected_paths)
        raise PackageVerificationError(
            f"package inventory mismatch; missing={missing!r}; undeclared={undeclared!r}"
        )

    for relative, path, expected_sha256 in verified_delivery:
        if _sha256_file(path) != expected_sha256:
            raise PackageVerificationError(f"delivery digest mismatch for {relative!r}")

    ordered_receipt_digests: list[str] = []
    for relative, path, expected in verified_receipts:
        receipt = _strict_json(path.read_bytes(), source=relative)
        claimed = receipt.pop("receipt_sha256", None)
        computed = _sha256_bytes(json.dumps(receipt, sort_keys=True, separators=(",", ":")).encode())
        if claimed != expected or computed != expected:
            raise PackageVerificationError(f"receipt digest mismatch for {relative!r}")
        ordered_receipt_digests.append(expected)

    if receipt_sequence != ordered_receipt_digests:
        raise PackageVerificationError("receipt sequence differs from the path-bound receipt inventory")

    return {
        "status": "pass",
        "schema": SCHEMA,
        "manifest_sha256": actual_manifest_sha256,
        "files_verified": len(files),
        "receipts_verified": len(receipt_files),
    }


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

    receipt_files: dict[str, str] = {}
    for index, item in enumerate(receipts):
        receipt_path = receipts_dir / f"{index:03d}-{item['stage']}.json"
        receipt_path.write_text(json.dumps(item, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        receipt_files[receipt_path.relative_to(root).as_posix()] = item["receipt_sha256"]

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
        "receipt_files": receipt_files,
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
    p.add_argument("input_obj", nargs="?")
    p.add_argument("output", nargs="?")
    p.add_argument("--uv", choices=("auto", "preserve", "box", "spherical"), default="auto")
    p.add_argument("--material-size", type=int, default=512)
    p.add_argument("--seed", type=int, default=1)
    p.add_argument("--verify", metavar="PACKAGE")
    p.add_argument("--expected-manifest-sha256")
    return p


if __name__ == "__main__":
    argument_parser = parser()
    args = argument_parser.parse_args()
    if args.verify:
        if args.input_obj or args.output or not args.expected_manifest_sha256:
            argument_parser.error("--verify requires --expected-manifest-sha256 and no build paths")
        result = verify_rigid_package(
            args.verify,
            expected_manifest_sha256=args.expected_manifest_sha256,
        )
    else:
        if not args.input_obj or not args.output or args.expected_manifest_sha256:
            argument_parser.error("build mode requires input_obj and output")
        result = build_rigid_package(args.input_obj, args.output, uv_mode=args.uv, material_size=args.material_size, seed=args.seed)
        result = {"manifest_sha256": result["manifest_sha256"], "delivery": result["delivery"], "truth": result["truth"]}
    print(json.dumps(result, indent=2))
