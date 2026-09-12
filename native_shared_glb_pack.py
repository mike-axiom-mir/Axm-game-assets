#!/usr/bin/env python3
"""Lossless GLB -> portable glTF package with shared content-addressed images.

Adapted from Universal Creation's finished RTS compact packer:
mike-axiom-mir/axm-universal-creation
commit a5cc708457b7e8f33e794fdac648ae65d15a0fb4
tools/blender/pack_rts_shared.py

This Game Asset Forge port hardens the donor mechanism with strict JSON, safe
create-only outputs, recursive bufferView reference preservation, explicit
receipts, and no Blender/runtime dependency. Geometry/accessor bytes and image
payloads are relocated byte-for-byte; no remeshing, optimization, or image
re-encoding occurs.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import struct
from typing import Any

SCHEMA = "axm.game-assets.shared-glb-pack/v0.1"
DONOR = {
    "repo": "mike-axiom-mir/axm-universal-creation",
    "commit": "a5cc708457b7e8f33e794fdac648ae65d15a0fb4",
    "mechanism": "tools/blender/pack_rts_shared.py",
}
SEMANTIC_SECTIONS = (
    "nodes",
    "meshes",
    "materials",
    "textures",
    "samplers",
    "animations",
    "skins",
    "scenes",
    "scene",
)
IMAGE_EXTENSIONS = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
}


class SharedGlbPackError(ValueError):
    pass


def _sha256(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _hex_digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _strict_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise SharedGlbPackError(f"duplicate JSON key: {key}")
        out[key] = value
    return out


def _reject_constant(value: str) -> None:
    raise SharedGlbPackError(f"non-finite JSON number: {value}")


def _parse_json(data: bytes) -> dict[str, Any]:
    try:
        value = json.loads(
            data.decode("utf-8"),
            object_pairs_hook=_strict_pairs,
            parse_constant=_reject_constant,
        )
    except SharedGlbPackError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as exc:
        raise SharedGlbPackError("GLB JSON chunk is invalid") from exc
    if not isinstance(value, dict):
        raise SharedGlbPackError("GLB JSON chunk must contain one object")
    return value


def read_glb(path: str | Path) -> tuple[bytes, dict[str, Any], bytes]:
    source = Path(path)
    try:
        source.lstat()
    except OSError as exc:
        raise SharedGlbPackError(f"source GLB is missing: {source}") from exc
    if source.is_symlink() or not source.is_file():
        raise SharedGlbPackError("source GLB must be a regular non-symlink file")
    raw = source.read_bytes()
    if len(raw) < 20:
        raise SharedGlbPackError("GLB is too short")
    magic, version, total = struct.unpack_from("<4sII", raw, 0)
    if magic != b"glTF" or version != 2 or total != len(raw):
        raise SharedGlbPackError("invalid GLB 2.0 header")
    position = 12
    document: dict[str, Any] | None = None
    binary_chunk: bytes | None = None
    seen_types: set[int] = set()
    while position < len(raw):
        if position + 8 > len(raw):
            raise SharedGlbPackError("truncated GLB chunk header")
        length, chunk_type = struct.unpack_from("<II", raw, position)
        start = position + 8
        end = start + length
        if end > len(raw):
            raise SharedGlbPackError("truncated GLB chunk payload")
        if chunk_type in seen_types:
            raise SharedGlbPackError("duplicate GLB JSON/BIN chunk type")
        seen_types.add(chunk_type)
        payload = raw[start:end]
        if chunk_type == 0x4E4F534A:
            document = _parse_json(payload.rstrip(b" \t\r\n\x00"))
        elif chunk_type == 0x004E4942:
            binary_chunk = payload
        else:
            raise SharedGlbPackError(f"unsupported GLB chunk type 0x{chunk_type:08x}")
        position = end
    if position != len(raw) or document is None or binary_chunk is None:
        raise SharedGlbPackError("GLB requires exactly one JSON and one BIN chunk")
    buffers = document.get("buffers")
    if (
        not isinstance(buffers, list)
        or len(buffers) != 1
        or not isinstance(buffers[0], dict)
        or "uri" in buffers[0]
    ):
        raise SharedGlbPackError("GLB must declare one embedded buffer")
    declared = buffers[0].get("byteLength")
    if (
        not isinstance(declared, int)
        or isinstance(declared, bool)
        or declared < 0
        or declared > len(binary_chunk)
        or len(binary_chunk) - declared > 3
    ):
        raise SharedGlbPackError("GLB buffer byteLength is invalid")
    return raw, document, binary_chunk[:declared]


def _view_blob(document: dict[str, Any], binary: bytes, index: int) -> bytes:
    views = document.get("bufferViews")
    if not isinstance(views, list) or not (0 <= index < len(views)):
        raise SharedGlbPackError(f"bufferView {index} is missing")
    view = views[index]
    if not isinstance(view, dict) or view.get("buffer") != 0:
        raise SharedGlbPackError(f"bufferView {index} must target buffer 0")
    offset = view.get("byteOffset", 0)
    length = view.get("byteLength")
    if (
        not isinstance(offset, int)
        or isinstance(offset, bool)
        or not isinstance(length, int)
        or isinstance(length, bool)
        or offset < 0
        or length < 0
        or offset + length > len(binary)
    ):
        raise SharedGlbPackError(f"bufferView {index} exceeds embedded buffer")
    return binary[offset : offset + length]


def _collect_buffer_view_refs(value: Any, *, skip_images: bool = False) -> set[int]:
    refs: set[int] = set()
    if isinstance(value, dict):
        for key, item in value.items():
            if skip_images and key == "images":
                continue
            if key == "bufferView":
                if not isinstance(item, int) or isinstance(item, bool) or item < 0:
                    raise SharedGlbPackError("bufferView reference must be a nonnegative integer")
                refs.add(item)
            else:
                refs.update(_collect_buffer_view_refs(item, skip_images=False))
    elif isinstance(value, list):
        for item in value:
            refs.update(_collect_buffer_view_refs(item, skip_images=False))
    return refs


def _remap_buffer_views(value: Any, remap: dict[int, int]) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if key == "bufferView":
                if item not in remap:
                    raise SharedGlbPackError(f"bufferView reference {item} was removed but is still referenced")
                value[key] = remap[item]
            else:
                _remap_buffer_views(item, remap)
    elif isinstance(value, list):
        for item in value:
            _remap_buffer_views(item, remap)


def _relative_uri(from_dir: Path, target: Path) -> str:
    return os.path.relpath(target, from_dir).replace(os.sep, "/")


def _write_create_only(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("xb") as handle:
            handle.write(payload)
    except FileExistsError as exc:
        raise SharedGlbPackError(f"refusing to overwrite output: {path}") from exc


def _write_shared_payload(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.is_symlink() or not path.is_file() or path.read_bytes() != payload:
            raise SharedGlbPackError(f"content-addressed payload path is occupied by different bytes: {path}")
        return
    _write_create_only(path, payload)


def pack_glb_to_shared(
    source_glb: str | Path,
    dest_gltf: str | Path,
    texture_root: str | Path,
) -> dict[str, Any]:
    source = Path(source_glb)
    dest = Path(dest_gltf)
    textures = Path(texture_root)
    if dest.suffix.lower() != ".gltf":
        raise SharedGlbPackError("destination must use .gltf")
    if dest.exists() or dest.with_suffix(".bin").exists():
        raise SharedGlbPackError("destination glTF/bin already exists")

    raw, original, binary = read_glb(source)
    document = copy.deepcopy(original)
    extensions = document.get("extensionsUsed", [])
    if extensions is None:
        extensions = []
    if not isinstance(extensions, list) or any(not isinstance(item, str) for item in extensions):
        raise SharedGlbPackError("extensionsUsed must be a string list")
    opaque = [
        item for item in extensions
        if any(token in item.lower() for token in ("meshopt", "draco", "compression"))
    ]
    if opaque:
        raise SharedGlbPackError(
            "compressed/opaque buffer extensions need a dedicated adapter: " + ", ".join(sorted(opaque))
        )

    images = document.get("images", [])
    if not isinstance(images, list) or not images:
        raise SharedGlbPackError("GLB must contain embedded images to share")
    image_views: set[int] = set()
    image_receipts: list[dict[str, Any]] = []
    for index, image in enumerate(images):
        if not isinstance(image, dict) or "uri" in image:
            raise SharedGlbPackError(f"image {index} must be bufferView-embedded")
        view_index = image.get("bufferView")
        mime = image.get("mimeType")
        if not isinstance(view_index, int) or isinstance(view_index, bool):
            raise SharedGlbPackError(f"image {index} has invalid bufferView")
        if mime not in IMAGE_EXTENSIONS:
            raise SharedGlbPackError(f"image {index} has unsupported mimeType {mime!r}")
        payload = _view_blob(original, binary, view_index)
        digest_hex = _hex_digest(payload)
        target = textures / (digest_hex + IMAGE_EXTENSIONS[mime])
        _write_shared_payload(target, payload)
        image.clear()
        image.update({
            "uri": _relative_uri(dest.parent, target),
            "mimeType": mime,
        })
        image_views.add(view_index)
        image_receipts.append({
            "image_index": index,
            "source_view": view_index,
            "sha256": "sha256:" + digest_hex,
            "bytes": len(payload),
            "mime": mime,
            "shared_path": target.name,
        })

    referenced_elsewhere = _collect_buffer_view_refs(original, skip_images=True)
    views = original.get("bufferViews")
    if not isinstance(views, list):
        raise SharedGlbPackError("GLB bufferViews are required")
    keep = [
        index for index in range(len(views))
        if index not in image_views or index in referenced_elsewhere
    ]
    remap = {old: new for new, old in enumerate(keep)}

    packed = bytearray()
    new_views: list[dict[str, Any]] = []
    view_receipts: list[dict[str, Any]] = []
    for old_index in keep:
        view = copy.deepcopy(views[old_index])
        payload = _view_blob(original, binary, old_index)
        while len(packed) % 4:
            packed.append(0)
        offset = len(packed)
        packed.extend(payload)
        view["buffer"] = 0
        view["byteOffset"] = offset
        view["byteLength"] = len(payload)
        new_views.append(view)
        view_receipts.append({
            "old_view": old_index,
            "new_view": remap[old_index],
            "sha256": _sha256(payload),
            "bytes": len(payload),
        })

    document["bufferViews"] = new_views
    _remap_buffer_views(document, remap)
    document["buffers"] = [{"uri": dest.stem + ".bin", "byteLength": len(packed)}]

    gltf_bytes = (
        json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        + b"\n"
    )
    bin_path = dest.with_suffix(".bin")
    _write_create_only(bin_path, bytes(packed))
    _write_create_only(dest, gltf_bytes)

    written = _parse_json(dest.read_bytes())
    out_binary = bin_path.read_bytes()
    for receipt in view_receipts:
        view = written["bufferViews"][receipt["new_view"]]
        offset = view.get("byteOffset", 0)
        chunk = out_binary[offset : offset + view["byteLength"]]
        if _sha256(chunk) != receipt["sha256"]:
            raise SharedGlbPackError("written geometry/accessor view differs from source")
    for image, receipt in zip(written.get("images", []), image_receipts):
        payload = (dest.parent / image["uri"]).resolve().read_bytes()
        if _sha256(payload) != receipt["sha256"]:
            raise SharedGlbPackError("written shared image differs from source")
    for key in SEMANTIC_SECTIONS:
        if written.get(key) != original.get(key):
            raise SharedGlbPackError(f"semantic section changed during lossless pack: {key}")

    report: dict[str, Any] = {
        "schema": SCHEMA,
        "status": "PASS",
        "source": {
            "path": source.name,
            "sha256": _sha256(raw),
            "bytes": len(raw),
        },
        "delivery": {
            "gltf": {
                "path": dest.name,
                "sha256": _sha256(dest.read_bytes()),
                "bytes": dest.stat().st_size,
            },
            "bin": {
                "path": bin_path.name,
                "sha256": _sha256(out_binary),
                "bytes": len(out_binary),
            },
            "shared_images": image_receipts,
        },
        "relocated_buffer_views": view_receipts,
        "semantic_sections_preserved": list(SEMANTIC_SECTIONS),
        "lossless_views_verified": True,
        "provenance": {
            "donor": DONOR,
            "implementation": "AXM Game Asset Forge hardened stdlib-only native adaptation",
        },
        "truth_boundary": {
            "proves": [
                "relocated kept bufferView payload bytes match their source payloads",
                "shared image payload bytes match their embedded source payloads",
                "listed semantic glTF sections remain structurally equal",
            ],
            "does_not_prove": [
                "visual quality",
                "engine performance",
                "semantic correctness of unknown extensions",
                "that lossy optimization occurred",
                "canonical adoption",
            ],
            "automatic_canon": False,
        },
    }
    report["report_digest"] = _sha256(
        json.dumps(report, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    )
    return report


def _safe_asset_id(value: str) -> str:
    if not value or "\\" in value:
        raise SharedGlbPackError("asset id must be a non-empty portable path segment")
    parsed = PurePosixPath(value)
    if parsed.is_absolute() or len(parsed.parts) != 1 or parsed.parts[0] in {".", ".."}:
        raise SharedGlbPackError(f"unsafe asset id {value!r}")
    return value


def pack_shared_collection(
    sources: dict[str, str | Path],
    output: str | Path,
) -> dict[str, Any]:
    if not sources:
        raise SharedGlbPackError("shared collection needs at least one source GLB")
    root = Path(output)
    if root.exists():
        raise SharedGlbPackError("shared collection destination must not already exist")
    root.mkdir(parents=True)
    textures = root / "textures"
    textures.mkdir()
    reports: dict[str, Any] = {}
    for asset_id in sorted(sources):
        safe_id = _safe_asset_id(asset_id)
        source = Path(sources[asset_id])
        report = pack_glb_to_shared(
            source,
            root / "assets" / safe_id / f"{safe_id}.gltf",
            textures,
        )
        reports[safe_id] = report
    manifest: dict[str, Any] = {
        "schema": "axm.game-assets.shared-glb-collection/v0.1",
        "status": "PASS",
        "assets": reports,
        "shared_texture_count": len([item for item in textures.iterdir() if item.is_file()]),
        "authority": {
            "canonical_mutation": False,
            "automatic_install": False,
            "release": False,
            "merge": False,
            "canon": False,
        },
        "provenance": {"donor": DONOR},
    }
    manifest["manifest_digest"] = _sha256(
        json.dumps(manifest, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    )
    (root / "packing-verification.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Losslessly unpack GLBs into shared-image glTF deliveries")
    parser.add_argument("output", type=Path)
    parser.add_argument("sources", nargs="+", type=Path)
    args = parser.parse_args(argv)
    mapping: dict[str, Path] = {}
    for source in args.sources:
        key = source.stem
        if key in mapping:
            raise SharedGlbPackError(f"duplicate source stem {key!r}")
        mapping[key] = source
    result = pack_shared_collection(mapping, args.output)
    print(json.dumps({
        "status": result["status"],
        "assets": len(result["assets"]),
        "shared_texture_count": result["shared_texture_count"],
        "manifest_digest": result["manifest_digest"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
