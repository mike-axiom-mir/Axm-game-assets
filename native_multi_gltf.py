#!/usr/bin/env python3
"""Dependency-free multi-primitive / multi-material glTF 2.0 compiler for AXM rigid assets."""
from __future__ import annotations

import json
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

from native_geometry import Mesh
from native_gltf import (
    _add_view,
    _align4,
    _expanded_triangles,
    _pack_vec,
    _sha256,
    _tangents,
    validate_gltf,
)
from native_uv import UVMap


@dataclass(frozen=True, slots=True)
class MaterialPrimitive:
    mesh: Mesh
    uvmap: UVMap
    material_name: str
    base_color_uri: str
    normal_uri: str
    orm_uri: str
    metallic_factor: float = 1.0
    roughness_factor: float = 1.0
    double_sided: bool = False


def compile_multi_gltf(
    primitives: Sequence[MaterialPrimitive],
    *,
    name: str,
    buffer_uri: str,
) -> tuple[dict[str, Any], bytes]:
    if not primitives:
        raise ValueError("multi glTF requires at least one primitive")

    blob = bytearray()
    views: list[dict[str, Any]] = []
    accessors: list[dict[str, Any]] = []
    gltf_primitives: list[dict[str, Any]] = []
    materials: list[dict[str, Any]] = []
    images: list[dict[str, Any]] = []
    textures: list[dict[str, Any]] = []
    total_triangles = 0
    total_compiled_vertices = 0

    def add_float_accessor(
        values: list[tuple[float, ...]],
        gltf_type: str,
        component_count: int,
        *,
        target: int = 34962,
        include_bounds: bool = False,
    ) -> int:
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

    for material_index, spec in enumerate(primitives):
        positions, normals, texcoords, indices = _expanded_triangles(spec.mesh, spec.uvmap)
        if not positions:
            raise ValueError(f"primitive {material_index} ({spec.mesh.name}) produced no triangles")
        tangents = _tangents(positions, normals, texcoords)

        position_accessor = add_float_accessor(positions, "VEC3", 3, include_bounds=True)
        normal_accessor = add_float_accessor(normals, "VEC3", 3)
        uv_accessor = add_float_accessor(texcoords, "VEC2", 2)
        tangent_accessor = add_float_accessor(tangents, "VEC4", 4)

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

        base_image = len(images)
        images.extend([
            {"uri": spec.base_color_uri},
            {"uri": spec.orm_uri},
            {"uri": spec.normal_uri},
        ])
        base_texture = len(textures)
        textures.extend([
            {"sampler": 0, "source": base_image},
            {"sampler": 0, "source": base_image + 1},
            {"sampler": 0, "source": base_image + 2},
        ])
        materials.append({
            "name": spec.material_name,
            "doubleSided": bool(spec.double_sided),
            "pbrMetallicRoughness": {
                "baseColorTexture": {"index": base_texture},
                "metallicRoughnessTexture": {"index": base_texture + 1},
                "metallicFactor": float(spec.metallic_factor),
                "roughnessFactor": float(spec.roughness_factor),
            },
            "normalTexture": {"index": base_texture + 2},
            "occlusionTexture": {"index": base_texture + 1},
        })
        gltf_primitives.append({
            "attributes": {
                "POSITION": position_accessor,
                "NORMAL": normal_accessor,
                "TEXCOORD_0": uv_accessor,
                "TANGENT": tangent_accessor,
            },
            "indices": index_accessor,
            "material": material_index,
            "mode": 4,
        })
        total_triangles += len(indices) // 3
        total_compiled_vertices += len(positions)

    _align4(blob)
    document: dict[str, Any] = {
        "asset": {"version": "2.0", "generator": "AXM Game Asset Forge native_multi_gltf v0.1"},
        "scene": 0,
        "scenes": [{"nodes": [0]}],
        "nodes": [{"name": name, "mesh": 0}],
        "meshes": [{"name": name, "primitives": gltf_primitives}],
        "buffers": [{"uri": buffer_uri, "byteLength": len(blob)}],
        "bufferViews": views,
        "accessors": accessors,
        "samplers": [{"magFilter": 9729, "minFilter": 9987, "wrapS": 10497, "wrapT": 10497}],
        "images": images,
        "textures": textures,
        "materials": materials,
        "extras": {
            "axm": {
                "compiler": "native_multi_gltf",
                "primitive_count": len(gltf_primitives),
                "material_count": len(materials),
                "triangles": total_triangles,
                "compiled_vertices": total_compiled_vertices,
                "truth": "Rigid multi-primitive delivery. Each material group owns explicit mesh/UV/material state. Skeleton, morphs, animation and material-quality judgment remain separate gates.",
            }
        },
    }
    return document, bytes(blob)


def write_multi_gltf(
    primitives: Sequence[MaterialPrimitive],
    output: str | Path,
    *,
    name: str,
) -> dict[str, Any]:
    root = Path(output)
    root.mkdir(parents=True, exist_ok=True)
    for spec in primitives:
        for uri in (spec.base_color_uri, spec.normal_uri, spec.orm_uri):
            if not (root / uri).exists():
                raise FileNotFoundError(root / uri)

    binary_name = f"{name}.bin"
    gltf_name = f"{name}.gltf"
    document, binary = compile_multi_gltf(primitives, name=name, buffer_uri=binary_name)
    (root / binary_name).write_bytes(binary)
    gltf_bytes = (json.dumps(document, indent=2, sort_keys=True) + "\n").encode("utf-8")
    (root / gltf_name).write_bytes(gltf_bytes)
    report = validate_gltf(document, binary, root)
    if report["status"] != "pass":
        raise ValueError(f"multi-material glTF failed internal structural validation: {report}")
    return {
        "gltf": gltf_name,
        "binary": binary_name,
        "gltf_sha256": _sha256(gltf_bytes),
        "binary_sha256": _sha256(binary),
        "validation": report,
        "triangles": document["extras"]["axm"]["triangles"],
        "compiled_vertices": document["extras"]["axm"]["compiled_vertices"],
        "primitive_count": document["extras"]["axm"]["primitive_count"],
        "material_count": document["extras"]["axm"]["material_count"],
        "material_names": [item["name"] for item in document["materials"]],
    }
