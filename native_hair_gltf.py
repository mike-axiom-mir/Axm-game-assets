#!/usr/bin/env python3
"""AXM dependency-free alpha-card hair glTF 2.0 compiler v0.2."""
from __future__ import annotations

import hashlib
import json
import struct
from pathlib import Path
from typing import Any

from native_geometry import Mesh
from native_gltf import _add_view, _align4, _expanded_triangles, _pack_vec, _tangents, validate_gltf
from native_uv import UVMap


def _sha(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def compile_hair_gltf(
    mesh: Mesh,
    uvmap: UVMap,
    *,
    buffer_uri: str,
    base_color_alpha_uri: str,
    orm_uri: str,
    alpha_cutoff: float = 0.34,
) -> tuple[dict[str, Any], bytes]:
    positions, normals, texcoords, indices = _expanded_triangles(mesh, uvmap)
    if not positions:
        raise ValueError("hair cards produced no triangles")
    tangents = _tangents(positions, normals, texcoords)
    blob = bytearray()
    views: list[dict[str, Any]] = []
    accessors: list[dict[str, Any]] = []

    def add_float(values, gltf_type: str, width: int, *, target: int | None = 34962, bounds: bool = False) -> int:
        view = _add_view(blob, _pack_vec(values), views, target=target)
        accessor: dict[str, Any] = {
            "bufferView": view,
            "byteOffset": 0,
            "componentType": 5126,
            "count": len(values),
            "type": gltf_type,
        }
        if bounds:
            accessor["min"] = [min(row[i] for row in values) for i in range(width)]
            accessor["max"] = [max(row[i] for row in values) for i in range(width)]
        accessors.append(accessor)
        return len(accessors) - 1

    pos_accessor = add_float(positions, "VEC3", 3, bounds=True)
    normal_accessor = add_float(normals, "VEC3", 3)
    uv_accessor = add_float(texcoords, "VEC2", 2)
    tangent_accessor = add_float(tangents, "VEC4", 4)
    index_payload = struct.pack("<" + "I" * len(indices), *indices)
    index_view = _add_view(blob, index_payload, views, target=34963)
    accessors.append({
        "bufferView": index_view,
        "byteOffset": 0,
        "componentType": 5125,
        "count": len(indices),
        "type": "SCALAR",
        "min": [0],
        "max": [len(indices) - 1],
    })
    index_accessor = len(accessors) - 1
    _align4(blob)

    document = {
        "asset": {"version": "2.0", "generator": "AXM Game Asset Forge native_hair_gltf v0.2"},
        "scene": 0,
        "scenes": [{"nodes": [0]}],
        "nodes": [{"name": mesh.name, "mesh": 0}],
        "meshes": [{"name": mesh.name, "primitives": [{
            "attributes": {
                "POSITION": pos_accessor,
                "NORMAL": normal_accessor,
                "TEXCOORD_0": uv_accessor,
                "TANGENT": tangent_accessor,
            },
            "indices": index_accessor,
            "material": 0,
            "mode": 4,
        }]}],
        "buffers": [{"uri": buffer_uri, "byteLength": len(blob)}],
        "bufferViews": views,
        "accessors": accessors,
        "samplers": [{"magFilter": 9729, "minFilter": 9987, "wrapS": 10497, "wrapT": 10497}],
        "images": [{"uri": base_color_alpha_uri}, {"uri": orm_uri}],
        "textures": [{"sampler": 0, "source": 0}, {"sampler": 0, "source": 1}],
        "materials": [{
            "name": "AXM_Native_Hair_Card",
            "pbrMetallicRoughness": {
                "baseColorTexture": {"index": 0},
                "metallicRoughnessTexture": {"index": 1},
                "metallicFactor": 0.0,
                "roughnessFactor": 1.0,
            },
            "occlusionTexture": {"index": 1},
            "alphaMode": "MASK",
            "alphaCutoff": float(alpha_cutoff),
            "doubleSided": True,
        }],
        "extras": {
            "axm": {
                "compiler": "native_hair_gltf",
                "source_vertices": len(mesh.vertices),
                "compiled_vertices": len(positions),
                "triangles": len(indices) // 3,
                "alpha_card_hair": True,
                "metallic_factor": 0.0,
                "anisotropic_specular": "recommended when target renderer supports it",
                "truth": "Structural non-metal alpha-card delivery. Card sorting, scalp coverage, anisotropy and motion remain visual/in-engine gates.",
            }
        },
    }
    return document, bytes(blob)


def write_hair_gltf(mesh: Mesh, uvmap: UVMap, output: str | Path, *, texture_dir: str = "textures", alpha_cutoff: float = 0.34) -> dict[str, object]:
    root = Path(output)
    root.mkdir(parents=True, exist_ok=True)
    binary_name = f"{mesh.name}.bin"
    gltf_name = f"{mesh.name}.gltf"
    base_uri = f"{texture_dir}/base_color_alpha.png"
    orm_uri = f"{texture_dir}/orm.png"
    for uri in (base_uri, orm_uri):
        if not (root / uri).exists():
            raise FileNotFoundError(root / uri)
    document, binary = compile_hair_gltf(
        mesh,
        uvmap,
        buffer_uri=binary_name,
        base_color_alpha_uri=base_uri,
        orm_uri=orm_uri,
        alpha_cutoff=alpha_cutoff,
    )
    (root / binary_name).write_bytes(binary)
    gltf_bytes = (json.dumps(document, indent=2, sort_keys=True) + "\n").encode("utf-8")
    (root / gltf_name).write_bytes(gltf_bytes)
    report = validate_gltf(document, binary, root)
    if report["status"] != "pass":
        raise ValueError(f"hair glTF failed structural validation: {report}")
    return {
        "gltf": gltf_name,
        "binary": binary_name,
        "gltf_sha256": _sha(gltf_bytes),
        "binary_sha256": _sha(binary),
        "validation": report,
        "triangles": document["extras"]["axm"]["triangles"],
        "compiled_vertices": document["extras"]["axm"]["compiled_vertices"],
        "alpha_mode": document["materials"][0]["alphaMode"],
        "double_sided": document["materials"][0]["doubleSided"],
        "metallic_factor": document["materials"][0]["pbrMetallicRoughness"]["metallicFactor"],
    }
