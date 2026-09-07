#!/usr/bin/env python3
"""Dependency-free glTF 2.0 compiler for rigid AXM native meshes."""
from __future__ import annotations

import hashlib
import json
import struct
from pathlib import Path
from typing import Any

from native_geometry import Mesh, vertex_normals
from native_uv import UVMap, validate_uv


def _align4(data: bytearray) -> None:
    while len(data) % 4:
        data.append(0)


def _sha256(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _expanded_triangles(mesh: Mesh, uvmap: UVMap) -> tuple[list[tuple[float, float, float]], list[tuple[float, float, float]], list[tuple[float, float]], list[int]]:
    report = validate_uv(mesh, uvmap)
    if report["status"] != "pass":
        raise ValueError(f"invalid UV state: {report}")
    normals = vertex_normals(mesh)
    positions: list[tuple[float, float, float]] = []
    expanded_normals: list[tuple[float, float, float]] = []
    texcoords: list[tuple[float, float]] = []
    indices: list[int] = []

    for face, uvface in zip(mesh.faces, uvmap.face_uvs):
        if len(face) < 3:
            continue
        for corner in range(1, len(face) - 1):
            tri_corners = (0, corner, corner + 1)
            for local in tri_corners:
                vi = face[local]
                ui = uvface[local]
                positions.append(mesh.vertices[vi])
                expanded_normals.append(normals[vi])
                texcoords.append(uvmap.uvs[ui])
                indices.append(len(indices))
    return positions, expanded_normals, texcoords, indices


def _pack_vec(values: list[tuple[float, ...]]) -> bytes:
    flat = [component for row in values for component in row]
    return struct.pack("<" + "f" * len(flat), *flat)


def _add_view(blob: bytearray, payload: bytes, views: list[dict[str, Any]], *, target: int | None = None) -> int:
    _align4(blob)
    offset = len(blob)
    blob.extend(payload)
    view: dict[str, Any] = {"buffer": 0, "byteOffset": offset, "byteLength": len(payload)}
    if target is not None:
        view["target"] = target
    views.append(view)
    return len(views) - 1


def compile_gltf(mesh: Mesh, uvmap: UVMap, *, buffer_uri: str, base_color_uri: str, normal_uri: str, orm_uri: str) -> tuple[dict[str, Any], bytes]:
    positions, normals, texcoords, indices = _expanded_triangles(mesh, uvmap)
    if not positions:
        raise ValueError("mesh produced no triangles")

    blob = bytearray()
    views: list[dict[str, Any]] = []
    accessors: list[dict[str, Any]] = []

    def add_float_accessor(values: list[tuple[float, ...]], gltf_type: str, component_count: int, *, target: int = 34962, include_bounds: bool = False) -> int:
        view_index = _add_view(blob, _pack_vec(values), views, target=target)
        accessor: dict[str, Any] = {
            "bufferView": view_index,
            "byteOffset": 0,
            "componentType": 5126,
            "count": len(values),
            "type": gltf_type,
        }
        if include_bounds:
            accessor["min"] = [min(row[i] for row in values) for i in range(component_count)]
            accessor["max"] = [max(row[i] for row in values) for i in range(component_count)]
        accessors.append(accessor)
        return len(accessors) - 1

    position_accessor = add_float_accessor(positions, "VEC3", 3, include_bounds=True)
    normal_accessor = add_float_accessor(normals, "VEC3", 3)
    uv_accessor = add_float_accessor(texcoords, "VEC2", 2)

    index_payload = struct.pack("<" + "I" * len(indices), *indices)
    index_view = _add_view(blob, index_payload, views, target=34963)
    accessors.append({
        "bufferView": index_view,
        "byteOffset": 0,
        "componentType": 5125,
        "count": len(indices),
        "type": "SCALAR",
        "min": [min(indices)],
        "max": [max(indices)],
    })
    index_accessor = len(accessors) - 1
    _align4(blob)

    document: dict[str, Any] = {
        "asset": {"version": "2.0", "generator": "AXM Game Asset Forge native_gltf v0.1"},
        "scene": 0,
        "scenes": [{"nodes": [0]}],
        "nodes": [{"name": mesh.name, "mesh": 0}],
        "meshes": [{"name": mesh.name, "primitives": [{
            "attributes": {"POSITION": position_accessor, "NORMAL": normal_accessor, "TEXCOORD_0": uv_accessor},
            "indices": index_accessor,
            "material": 0,
            "mode": 4,
        }]}],
        "buffers": [{"uri": buffer_uri, "byteLength": len(blob)}],
        "bufferViews": views,
        "accessors": accessors,
        "samplers": [{"magFilter": 9729, "minFilter": 9987, "wrapS": 10497, "wrapT": 10497}],
        "images": [{"uri": base_color_uri}, {"uri": orm_uri}, {"uri": normal_uri}],
        "textures": [{"sampler": 0, "source": 0}, {"sampler": 0, "source": 1}, {"sampler": 0, "source": 2}],
        "materials": [{
            "name": "AXM_Native_PaintedMetal",
            "pbrMetallicRoughness": {
                "baseColorTexture": {"index": 0},
                "metallicRoughnessTexture": {"index": 1},
                "metallicFactor": 1.0,
                "roughnessFactor": 1.0,
            },
            "normalTexture": {"index": 2},
            "occlusionTexture": {"index": 1},
        }],
        "extras": {
            "axm": {
                "compiler": "native_gltf",
                "uv_method": uvmap.method,
                "source_vertices": len(mesh.vertices),
                "compiled_vertices": len(positions),
                "triangles": len(indices) // 3,
                "truth": "Rigid mesh only. No skeleton, morph targets, tangent channel, animation, or skinning in v0.1.",
            }
        },
    }
    return document, bytes(blob)


def validate_gltf(document: dict[str, Any], binary: bytes, root: str | Path | None = None) -> dict[str, Any]:
    failures: list[str] = []
    if document.get("asset", {}).get("version") != "2.0":
        failures.append("asset.version must be 2.0")
    buffers = document.get("buffers", [])
    if len(buffers) != 1:
        failures.append("native v0.1 expects exactly one buffer")
    elif buffers[0].get("byteLength") != len(binary):
        failures.append("buffer byteLength mismatch")
    views = document.get("bufferViews", [])
    for index, view in enumerate(views):
        start = int(view.get("byteOffset", 0))
        length = int(view.get("byteLength", 0))
        if start < 0 or length < 0 or start + length > len(binary):
            failures.append(f"bufferView {index} outside binary")
    accessors = document.get("accessors", [])
    for index, accessor in enumerate(accessors):
        view = accessor.get("bufferView")
        if not isinstance(view, int) or view < 0 or view >= len(views):
            failures.append(f"accessor {index} bad bufferView")
        if int(accessor.get("count", 0)) <= 0:
            failures.append(f"accessor {index} empty")
    if root is not None:
        root_path = Path(root)
        for image in document.get("images", []):
            uri = image.get("uri")
            if not uri or not (root_path / uri).exists():
                failures.append(f"missing image {uri}")
        if buffers:
            uri = buffers[0].get("uri")
            if not uri or not (root_path / uri).exists():
                failures.append(f"missing buffer {uri}")
    return {"status": "pass" if not failures else "fail", "failures": failures}


def write_gltf(mesh: Mesh, uvmap: UVMap, output: str | Path, *, texture_dir: str = "textures") -> dict[str, Any]:
    root = Path(output)
    root.mkdir(parents=True, exist_ok=True)
    binary_name = f"{mesh.name}.bin"
    gltf_name = f"{mesh.name}.gltf"
    base_uri = f"{texture_dir}/base_color.png"
    normal_uri = f"{texture_dir}/normal.png"
    orm_uri = f"{texture_dir}/orm.png"
    for uri in (base_uri, normal_uri, orm_uri):
        if not (root / uri).exists():
            raise FileNotFoundError(root / uri)

    document, binary = compile_gltf(
        mesh,
        uvmap,
        buffer_uri=binary_name,
        base_color_uri=base_uri,
        normal_uri=normal_uri,
        orm_uri=orm_uri,
    )
    (root / binary_name).write_bytes(binary)
    gltf_bytes = (json.dumps(document, indent=2, sort_keys=True) + "\n").encode()
    (root / gltf_name).write_bytes(gltf_bytes)
    report = validate_gltf(document, binary, root)
    if report["status"] != "pass":
        raise ValueError(f"compiled glTF failed internal validation: {report}")
    return {
        "gltf": gltf_name,
        "binary": binary_name,
        "gltf_sha256": _sha256(gltf_bytes),
        "binary_sha256": _sha256(binary),
        "validation": report,
        "triangles": document["extras"]["axm"]["triangles"],
        "compiled_vertices": document["extras"]["axm"]["compiled_vertices"],
    }
