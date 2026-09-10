#!/usr/bin/env python3
"""Derive a deterministic single-file GLB from one verified native rigid package.

The source package remains unchanged. This module first requires the caller-owned
manifest digest accepted by native_pipeline.verify_rigid_package, then embeds the
package's declared glTF buffer and PNG textures into a new GLB delivery.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import struct
from copy import deepcopy
from pathlib import Path, PurePosixPath
from typing import Any

from native_pipeline import PackageVerificationError, verify_rigid_package

DELIVERY_SCHEMA = "axm.game-assets.verified-glb-delivery/v0.1"
RTS_REQUEST_CONTRACT = "axm.rts.forge-unit-request/v0.1"
READY_STATE = "READY_FOR_EXPLICIT_CONSUMER_LOAD"


class GlbDeliveryError(ValueError):
    """Raised when verified package evidence cannot become a bounded GLB delivery."""


def _sha256_bytes(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _canonical_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _strict_json(data: bytes, *, source: str) -> dict[str, Any]:
    def reject_duplicates(pairs):
        value: dict[str, Any] = {}
        for key, item in pairs:
            if key in value:
                raise GlbDeliveryError(f"{source} contains duplicate key {key!r}")
            value[key] = item
        return value

    try:
        parsed = json.loads(data, object_pairs_hook=reject_duplicates)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise GlbDeliveryError(f"{source} is not valid UTF-8 JSON") from exc
    if not isinstance(parsed, dict):
        raise GlbDeliveryError(f"{source} must contain one JSON object")
    return parsed


def _safe_relative(value: Any, *, label: str) -> PurePosixPath:
    if not isinstance(value, str) or not value or "\\" in value:
        raise GlbDeliveryError(f"{label} must be one safe relative POSIX path")
    raw = value.split("/")
    parsed = PurePosixPath(value)
    if parsed.is_absolute() or any(part in {"", ".", ".."} for part in raw) or parsed.as_posix() != value:
        raise GlbDeliveryError(f"{label} is unsafe: {value!r}")
    return parsed


def _declared_file(root: Path, manifest: dict[str, Any], relative: str, *, label: str) -> tuple[Path, bytes, str]:
    path = _safe_relative(relative, label=label)
    files = manifest.get("files")
    if not isinstance(files, dict) or relative not in files:
        raise GlbDeliveryError(f"{label} is not declared by the verified package inventory")
    expected = files[relative]
    if not isinstance(expected, str) or not expected.startswith("sha256:"):
        raise GlbDeliveryError(f"{label} has no valid package digest")
    absolute = root.joinpath(*path.parts)
    if absolute.is_symlink() or not absolute.is_file():
        raise GlbDeliveryError(f"{label} is not a regular package file")
    data = absolute.read_bytes()
    actual = _sha256_bytes(data)
    if actual != expected:
        raise GlbDeliveryError(f"{label} changed after package verification")
    return absolute, data, actual


def _pad4(data: bytes, pad_byte: bytes) -> bytes:
    remainder = len(data) % 4
    return data if remainder == 0 else data + pad_byte * (4 - remainder)


def _append_aligned(blob: bytearray, payload: bytes) -> tuple[int, int]:
    while len(blob) % 4:
        blob.append(0)
    offset = len(blob)
    blob.extend(payload)
    return offset, len(payload)


def _parse_glb(glb: bytes) -> tuple[dict[str, Any], bytes]:
    if len(glb) < 20:
        raise GlbDeliveryError("GLB is shorter than its required header/chunk boundary")
    magic, version, total = struct.unpack_from("<4sII", glb, 0)
    if magic != b"glTF" or version != 2 or total != len(glb):
        raise GlbDeliveryError("GLB header is invalid")
    json_len, json_type = struct.unpack_from("<II", glb, 12)
    if json_type != 0x4E4F534A:
        raise GlbDeliveryError("GLB first chunk is not JSON")
    json_start = 20
    json_end = json_start + json_len
    if json_end + 8 > len(glb):
        raise GlbDeliveryError("GLB JSON chunk exceeds file bounds")
    try:
        document = json.loads(glb[json_start:json_end].rstrip(b" \t\r\n\x00").decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise GlbDeliveryError("GLB JSON chunk is invalid") from exc
    if not isinstance(document, dict):
        raise GlbDeliveryError("GLB JSON chunk must be an object")
    bin_len, bin_type = struct.unpack_from("<II", glb, json_end)
    if bin_type != 0x004E4942:
        raise GlbDeliveryError("GLB second chunk is not BIN")
    bin_start = json_end + 8
    bin_end = bin_start + bin_len
    if bin_end != len(glb):
        raise GlbDeliveryError("GLB BIN chunk length does not match file length")
    buffers = document.get("buffers")
    if not isinstance(buffers, list) or len(buffers) != 1 or not isinstance(buffers[0], dict):
        raise GlbDeliveryError("GLB must declare exactly one embedded buffer")
    declared_len = buffers[0].get("byteLength")
    if not isinstance(declared_len, int) or declared_len < 0 or declared_len > bin_len or bin_len - declared_len > 3:
        raise GlbDeliveryError("GLB embedded buffer byteLength is invalid")
    return document, glb[bin_start:bin_start + declared_len]


def validate_glb_delivery(glb: bytes) -> dict[str, Any]:
    document, binary = _parse_glb(glb)
    if document.get("asset", {}).get("version") != "2.0":
        raise GlbDeliveryError("embedded glTF asset.version must be 2.0")
    if document.get("buffers", [{}])[0].get("uri") is not None:
        raise GlbDeliveryError("single-file GLB buffer must not retain an external URI")
    views = document.get("bufferViews")
    if not isinstance(views, list):
        raise GlbDeliveryError("GLB bufferViews are required")
    for index, view in enumerate(views):
        if not isinstance(view, dict) or view.get("buffer") != 0:
            raise GlbDeliveryError(f"bufferView {index} must target embedded buffer 0")
        offset = view.get("byteOffset", 0)
        length = view.get("byteLength")
        if not isinstance(offset, int) or not isinstance(length, int) or offset < 0 or length < 0 or offset + length > len(binary):
            raise GlbDeliveryError(f"bufferView {index} exceeds embedded buffer")
    images = document.get("images")
    if not isinstance(images, list) or not images:
        raise GlbDeliveryError("verified rigid GLB must embed its material images")
    for index, image in enumerate(images):
        if not isinstance(image, dict) or image.get("mimeType") != "image/png" or "uri" in image:
            raise GlbDeliveryError(f"image {index} must be one embedded PNG")
        view = image.get("bufferView")
        if not isinstance(view, int) or view < 0 or view >= len(views):
            raise GlbDeliveryError(f"image {index} has invalid bufferView")
    return {
        "status": "pass",
        "asset_version": "2.0",
        "buffer_bytes": len(binary),
        "buffer_views": len(views),
        "images_embedded": len(images),
    }


def _bind_rts_request(request_path: str | Path | None, *, asset_name: str) -> dict[str, Any] | None:
    if request_path is None:
        return None
    path = Path(request_path)
    if path.is_symlink() or not path.is_file():
        raise GlbDeliveryError("consumer request must be a regular file")
    request = _strict_json(path.read_bytes(), source="consumer request")
    if request.get("contract") != RTS_REQUEST_CONTRACT:
        raise GlbDeliveryError(f"unsupported consumer request contract {request.get('contract')!r}")
    asset = request.get("asset")
    targets = request.get("targets")
    if not isinstance(asset, dict) or not isinstance(targets, dict):
        raise GlbDeliveryError("consumer request is missing asset/targets")
    if asset.get("id") != asset_name:
        raise GlbDeliveryError("verified package asset identity does not match consumer request")
    if asset.get("type") != "rigid-proxy":
        raise GlbDeliveryError("native rigid GLB bridge accepts only explicit rigid-proxy requests")
    if targets.get("delivery") != ["glb"] or targets.get("engines") != ["threejs"]:
        raise GlbDeliveryError("consumer request must explicitly target threejs + glb")
    return {
        "contract": RTS_REQUEST_CONTRACT,
        "sha256": _sha256_bytes(_canonical_json(request)),
        "asset_id": asset_name,
        "asset_type": "rigid-proxy",
        "engine": "threejs",
        "delivery": "glb",
    }


def build_verified_glb_delivery(
    package: str | Path,
    output: str | Path,
    *,
    expected_manifest_sha256: str,
    consumer_request: str | Path | None = None,
) -> dict[str, Any]:
    """Verify one native rigid package, then derive one deterministic self-contained GLB."""
    try:
        package_result = verify_rigid_package(package, expected_manifest_sha256=expected_manifest_sha256)
    except PackageVerificationError as exc:
        raise GlbDeliveryError(f"source package verification failed: {exc}") from exc
    if package_result.get("status") != "pass":
        raise GlbDeliveryError("source package did not pass provider verification")

    root = Path(package)
    manifest_path = root / "package-manifest.json"
    manifest = _strict_json(manifest_path.read_bytes(), source="package-manifest.json")
    delivery = manifest.get("delivery")
    asset = manifest.get("asset")
    if not isinstance(delivery, dict) or not isinstance(asset, dict) or not isinstance(asset.get("name"), str):
        raise GlbDeliveryError("verified package lacks native delivery/asset metadata")
    if delivery.get("validation", {}).get("status") != "pass":
        raise GlbDeliveryError("source glTF delivery was not provider-validated")

    gltf_name = delivery.get("gltf")
    binary_name = delivery.get("binary")
    if not isinstance(gltf_name, str) or not isinstance(binary_name, str):
        raise GlbDeliveryError("source delivery does not declare glTF and binary paths")
    _, gltf_bytes, gltf_sha = _declared_file(root, manifest, gltf_name, label="source glTF")
    _, geometry_bytes, binary_sha = _declared_file(root, manifest, binary_name, label="source binary")
    if delivery.get("gltf_sha256") != gltf_sha or delivery.get("binary_sha256") != binary_sha:
        raise GlbDeliveryError("delivery metadata does not match verified package inventory")

    source_doc = _strict_json(gltf_bytes, source=gltf_name)
    buffers = source_doc.get("buffers")
    if not isinstance(buffers, list) or len(buffers) != 1 or buffers[0].get("uri") != binary_name:
        raise GlbDeliveryError("native glTF buffer URI is not bound to the verified binary")
    if buffers[0].get("byteLength") != len(geometry_bytes):
        raise GlbDeliveryError("native glTF buffer byteLength differs from verified binary")

    document = deepcopy(source_doc)
    combined = bytearray(geometry_bytes)
    image_receipts: list[dict[str, Any]] = []
    images = document.get("images")
    if not isinstance(images, list) or not images:
        raise GlbDeliveryError("native glTF declares no material images")
    for index, image in enumerate(images):
        if not isinstance(image, dict):
            raise GlbDeliveryError(f"image {index} is malformed")
        uri = image.get("uri")
        if not isinstance(uri, str) or not uri.lower().endswith(".png"):
            raise GlbDeliveryError(f"image {index} must reference a package PNG")
        _, payload, digest = _declared_file(root, manifest, uri, label=f"image {index}")
        if not payload.startswith(b"\x89PNG\r\n\x1a\n"):
            raise GlbDeliveryError(f"image {index} is not a PNG")
        offset, length = _append_aligned(combined, payload)
        document.setdefault("bufferViews", []).append({"buffer": 0, "byteOffset": offset, "byteLength": length})
        image.clear()
        image.update({"bufferView": len(document["bufferViews"]) - 1, "mimeType": "image/png"})
        image_receipts.append({"path": uri, "sha256": digest, "bytes": length})

    document["buffers"] = [{"byteLength": len(combined)}]
    asset_extras = document.setdefault("asset", {}).setdefault("extras", {})
    asset_extras["axm_verified_delivery"] = {
        "schema": DELIVERY_SCHEMA,
        "source_manifest_sha256": expected_manifest_sha256,
    }

    json_payload = _pad4(_canonical_json(document), b" ")
    bin_payload = _pad4(bytes(combined), b"\x00")
    total = 12 + 8 + len(json_payload) + 8 + len(bin_payload)
    glb = b"".join([
        struct.pack("<4sII", b"glTF", 2, total),
        struct.pack("<II", len(json_payload), 0x4E4F534A),
        json_payload,
        struct.pack("<II", len(bin_payload), 0x004E4942),
        bin_payload,
    ])
    validation = validate_glb_delivery(glb)

    consumer = _bind_rts_request(consumer_request, asset_name=asset["name"])
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(glb)

    receipt = {
        "schema": DELIVERY_SCHEMA,
        "status": READY_STATE,
        "source": {
            "package_schema": manifest.get("schema"),
            "manifest_sha256": expected_manifest_sha256,
            "gltf": {"path": gltf_name, "sha256": gltf_sha, "bytes": len(gltf_bytes)},
            "binary": {"path": binary_name, "sha256": binary_sha, "bytes": len(geometry_bytes)},
            "images": image_receipts,
        },
        "asset": {"name": asset["name"]},
        "consumer_request": consumer,
        "delivery": {
            "format": "glb",
            "sha256": _sha256_bytes(glb),
            "bytes": len(glb),
            "self_contained": True,
            "validation": validation,
        },
        "authority": {
            "canonical_genome_mutation": False,
            "source_package_mutation": False,
            "automatic_consumer_install": False,
            "automatic_runtime_adoption": False,
            "visual_approval": False,
            "merge": False,
            "canon": False,
        },
        "truth": {
            "rigid_snapshot_only": True,
            "skeleton_or_animation_claim": False,
            "consumer_request_binding_is_compatibility_evidence_not_visual_fitness": True,
        },
    }
    return receipt


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Derive one verified, self-contained rigid GLB delivery")
    p.add_argument("--package", required=True)
    p.add_argument("--expected-manifest-sha256", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--receipt")
    p.add_argument("--consumer-request")
    return p


def main() -> int:
    args = parser().parse_args()
    try:
        receipt = build_verified_glb_delivery(
            args.package,
            args.output,
            expected_manifest_sha256=args.expected_manifest_sha256,
            consumer_request=args.consumer_request,
        )
    except GlbDeliveryError as exc:
        raise SystemExit(f"GLB delivery rejected: {exc}")
    if args.receipt:
        Path(args.receipt).write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
