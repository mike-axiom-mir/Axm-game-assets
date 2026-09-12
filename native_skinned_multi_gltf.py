#!/usr/bin/env python3
"""Dependency-free multi-material skinned glTF 2.0 compiler for AXM characters.

This is the reusable bridge between the existing single-material character
compiler and the multi-material rigid compiler. Every primitive keeps its own
mesh/UV/material/skin state while sharing one skeleton and animation set.

Passing this structural gate does not prove visual quality, deformation quality,
engine performance, gameplay fit, or CANON.
"""
from __future__ import annotations

import json
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

from native_animation import AnimationClip, validate_animation_clip
from native_geometry import Mesh, vertex_normals
from native_gltf import _add_view, _align4, _pack_vec, _sha256, _tangents, validate_gltf
from native_skin import (
    Skeleton,
    SkinWeights,
    flatten_matrix_column_major,
    inverse_bind_matrices,
    validate_skeleton,
    validate_skin_weights,
)
from native_uv import UVMap, validate_uv


@dataclass(frozen=True, slots=True)
class SkinnedMaterialPrimitive:
    mesh: Mesh
    uvmap: UVMap
    skin_weights: SkinWeights
    material_name: str
    base_color_uri: str
    normal_uri: str
    orm_uri: str
    metallic_factor: float = 1.0
    roughness_factor: float = 1.0
    double_sided: bool = False
    base_color_factor: tuple[float, float, float, float] = (1.0, 1.0, 1.0, 1.0)
    alpha_mode: str | None = None
    alpha_cutoff: float | None = None
    semantic_role: str = "character-surface"


def rigid_skin_weights(mesh: Mesh, joint_index: int) -> SkinWeights:
    """Bind every vertex of a rigid accessory to exactly one skeleton joint."""
    if type(joint_index) is not int or joint_index < 0:
        raise ValueError("joint_index must be a non-negative integer")
    return SkinWeights(
        [(joint_index, 0, 0, 0) for _ in mesh.vertices],
        [(1.0, 0.0, 0.0, 0.0) for _ in mesh.vertices],
    )


def _expanded(mesh: Mesh, uvmap: UVMap):
    report = validate_uv(mesh, uvmap)
    if report["status"] != "pass":
        raise ValueError(f"invalid UV state: {report}")
    normals = vertex_normals(mesh)
    positions = []
    expanded_normals = []
    texcoords = []
    indices = []
    source_indices = []
    for face, uvface in zip(mesh.faces, uvmap.face_uvs):
        if len(face) < 3:
            continue
        for corner in range(1, len(face) - 1):
            for local in (0, corner, corner + 1):
                vertex_index = face[local]
                uv_index = uvface[local]
                positions.append(mesh.vertices[vertex_index])
                expanded_normals.append(normals[vertex_index])
                texcoords.append(uvmap.uvs[uv_index])
                source_indices.append(vertex_index)
                indices.append(len(indices))
    return positions, expanded_normals, texcoords, indices, source_indices


def _pack_u16_vec4(values: Sequence[tuple[int, int, int, int]]) -> bytes:
    flat = [component for row in values for component in row]
    if any(value < 0 or value > 65535 for value in flat):
        raise ValueError("joint index exceeds unsigned-short glTF storage")
    return struct.pack("<" + "H" * len(flat), *flat)


def compile_skinned_multi_gltf(
    primitives: Sequence[SkinnedMaterialPrimitive],
    skeleton: Skeleton,
    animations: Sequence[AnimationClip] = (),
    *,
    name: str,
    buffer_uri: str,
) -> tuple[dict[str, Any], bytes]:
    if not primitives:
        raise ValueError("skinned multi glTF requires at least one primitive")
    if not name.strip():
        raise ValueError("character name must be non-empty")

    skeleton_report = validate_skeleton(skeleton)
    if skeleton_report["status"] != "pass":
        raise ValueError(f"invalid skeleton: {skeleton_report}")
    for clip in animations:
        report = validate_animation_clip(clip, skeleton)
        if report["status"] != "pass":
            raise ValueError(f"invalid animation {clip.name}: {report}")

    blob = bytearray()
    views: list[dict[str, Any]] = []
    accessors: list[dict[str, Any]] = []
    gltf_primitives: list[dict[str, Any]] = []
    materials: list[dict[str, Any]] = []
    images: list[dict[str, Any]] = []
    textures: list[dict[str, Any]] = []
    primitive_evidence: list[dict[str, Any]] = []
    total_triangles = 0
    total_compiled_vertices = 0

    def add_float(
        values: Sequence[tuple[float, ...]],
        gltf_type: str,
        component_count: int,
        *,
        target: int | None = 34962,
        include_bounds: bool = False,
    ) -> int:
        rows = [tuple(float(value) for value in row) for row in values]
        view_index = _add_view(blob, _pack_vec(rows), views, target=target)
        accessor: dict[str, Any] = {
            "bufferView": view_index,
            "byteOffset": 0,
            "componentType": 5126,
            "count": len(rows),
            "type": gltf_type,
        }
        if include_bounds:
            accessor["min"] = [min(row[i] for row in rows) for i in range(component_count)]
            accessor["max"] = [max(row[i] for row in rows) for i in range(component_count)]
        accessors.append(accessor)
        return len(accessors) - 1

    for material_index, spec in enumerate(primitives):
        if not spec.material_name.strip():
            raise ValueError(f"primitive {material_index} needs a material name")
        if spec.alpha_mode not in (None, "OPAQUE", "MASK", "BLEND"):
            raise ValueError(f"unsupported alpha mode {spec.alpha_mode!r}")
        if spec.alpha_cutoff is not None and spec.alpha_mode != "MASK":
            raise ValueError("alpha_cutoff is only valid with alpha_mode='MASK'")
        if len(spec.base_color_factor) != 4 or any(
            value < 0.0 or value > 1.0 for value in spec.base_color_factor
        ):
            raise ValueError("base_color_factor must contain four values within [0,1]")

        weight_report = validate_skin_weights(
            spec.skin_weights,
            vertex_count=len(spec.mesh.vertices),
            joint_count=len(skeleton.joints),
        )
        if weight_report["status"] != "pass":
            raise ValueError(f"primitive {material_index} has invalid skin weights: {weight_report}")

        positions, normals, texcoords, indices, source_indices = _expanded(spec.mesh, spec.uvmap)
        if not positions:
            raise ValueError(f"primitive {material_index} ({spec.mesh.name}) produced no triangles")
        tangents = _tangents(positions, normals, texcoords)
        expanded_joints = [spec.skin_weights.joints[index] for index in source_indices]
        expanded_weights = [spec.skin_weights.weights[index] for index in source_indices]

        position_accessor = add_float(positions, "VEC3", 3, include_bounds=True)
        normal_accessor = add_float(normals, "VEC3", 3)
        uv_accessor = add_float(texcoords, "VEC2", 2)
        tangent_accessor = add_float(tangents, "VEC4", 4)

        joint_view = _add_view(blob, _pack_u16_vec4(expanded_joints), views, target=34962)
        accessors.append({
            "bufferView": joint_view,
            "byteOffset": 0,
            "componentType": 5123,
            "count": len(expanded_joints),
            "type": "VEC4",
        })
        joints_accessor = len(accessors) - 1
        weights_accessor = add_float(expanded_weights, "VEC4", 4)

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

        material: dict[str, Any] = {
            "name": spec.material_name,
            "doubleSided": bool(spec.double_sided),
            "pbrMetallicRoughness": {
                "baseColorTexture": {"index": base_texture},
                "baseColorFactor": [float(value) for value in spec.base_color_factor],
                "metallicRoughnessTexture": {"index": base_texture + 1},
                "metallicFactor": float(spec.metallic_factor),
                "roughnessFactor": float(spec.roughness_factor),
            },
            "normalTexture": {"index": base_texture + 2},
            "occlusionTexture": {"index": base_texture + 1},
        }
        if spec.alpha_mode is not None:
            material["alphaMode"] = spec.alpha_mode
        if spec.alpha_cutoff is not None:
            material["alphaCutoff"] = float(spec.alpha_cutoff)
        materials.append(material)

        gltf_primitives.append({
            "attributes": {
                "POSITION": position_accessor,
                "NORMAL": normal_accessor,
                "TEXCOORD_0": uv_accessor,
                "TANGENT": tangent_accessor,
                "JOINTS_0": joints_accessor,
                "WEIGHTS_0": weights_accessor,
            },
            "indices": index_accessor,
            "material": material_index,
            "mode": 4,
            "extras": {
                "axm": {
                    "source_mesh": spec.mesh.name,
                    "semantic_role": spec.semantic_role,
                }
            },
        })
        triangle_count = len(indices) // 3
        total_triangles += triangle_count
        total_compiled_vertices += len(positions)
        primitive_evidence.append({
            "mesh": spec.mesh.name,
            "semantic_role": spec.semantic_role,
            "material": spec.material_name,
            "source_vertices": len(spec.mesh.vertices),
            "compiled_vertices": len(positions),
            "triangles": triangle_count,
            "skin_validation": weight_report,
        })

    inverse_binds = [flatten_matrix_column_major(matrix) for matrix in inverse_bind_matrices(skeleton)]
    inverse_bind_accessor = add_float(inverse_binds, "MAT4", 16, target=None)

    animation_entries: list[dict[str, Any]] = []
    path_types = {"translation": ("VEC3", 3), "rotation": ("VEC4", 4), "scale": ("VEC3", 3)}
    for clip in animations:
        samplers: list[dict[str, Any]] = []
        channels: list[dict[str, Any]] = []
        for track in clip.tracks:
            input_accessor = add_float(
                [(float(time),) for time in track.times],
                "SCALAR",
                1,
                target=None,
                include_bounds=True,
            )
            output_type, output_width = path_types[track.path]
            output_accessor = add_float(
                [tuple(float(component) for component in value) for value in track.values],
                output_type,
                output_width,
                target=None,
            )
            sampler_index = len(samplers)
            samplers.append({
                "input": input_accessor,
                "output": output_accessor,
                "interpolation": track.interpolation,
            })
            channels.append({
                "sampler": sampler_index,
                "target": {"node": track.joint + 1, "path": track.path},
            })
        animation_entries.append({"name": clip.name, "samplers": samplers, "channels": channels})

    _align4(blob)

    nodes: list[dict[str, Any]] = [{"name": name, "mesh": 0, "skin": 0}]
    for joint in skeleton.joints:
        nodes.append({
            "name": joint.name,
            "translation": list(joint.translation),
            "rotation": list(joint.rotation),
            "scale": list(joint.scale),
        })
    for index, joint in enumerate(skeleton.joints):
        if joint.parent is not None:
            nodes[joint.parent + 1].setdefault("children", []).append(index + 1)
    root_joint = int(skeleton_report["roots"][0])

    document: dict[str, Any] = {
        "asset": {"version": "2.0", "generator": "AXM Game Asset Forge native_skinned_multi_gltf v0.1"},
        "scene": 0,
        "scenes": [{"nodes": [0, root_joint + 1]}],
        "nodes": nodes,
        "meshes": [{"name": name, "primitives": gltf_primitives}],
        "skins": [{
            "name": f"{name}_skin",
            "inverseBindMatrices": inverse_bind_accessor,
            "joints": [index + 1 for index in range(len(skeleton.joints))],
            "skeleton": root_joint + 1,
        }],
        "buffers": [{"uri": buffer_uri, "byteLength": len(blob)}],
        "bufferViews": views,
        "accessors": accessors,
        "samplers": [{"magFilter": 9729, "minFilter": 9987, "wrapS": 10497, "wrapT": 10497}],
        "images": images,
        "textures": textures,
        "materials": materials,
        "animations": animation_entries,
        "extras": {
            "axm": {
                "compiler": "native_skinned_multi_gltf",
                "primitive_count": len(gltf_primitives),
                "material_count": len(materials),
                "source_vertices": sum(len(spec.mesh.vertices) for spec in primitives),
                "compiled_vertices": total_compiled_vertices,
                "triangles": total_triangles,
                "joints": len(skeleton.joints),
                "animations": [clip.name for clip in animations],
                "primitive_evidence": primitive_evidence,
                "truth": (
                    "Multi-material skinned character delivery. Every primitive has explicit UV/material/skin "
                    "state and shares one validated skeleton/animation set. Rigid accessories may be represented "
                    "by one-joint skinning. This is structural delivery evidence, not deformation, visual-quality, "
                    "engine-performance, gameplay, release, or CANON evidence."
                ),
            }
        },
    }
    return document, bytes(blob)


def write_skinned_multi_gltf(
    primitives: Sequence[SkinnedMaterialPrimitive],
    skeleton: Skeleton,
    output: str | Path,
    animations: Sequence[AnimationClip] = (),
    *,
    name: str,
) -> dict[str, Any]:
    root = Path(output)
    root.mkdir(parents=True, exist_ok=True)
    gltf_name = f"{name}.gltf"
    binary_name = f"{name}.bin"
    if (root / gltf_name).exists() or (root / binary_name).exists():
        raise FileExistsError("skinned character delivery is create-only")
    for spec in primitives:
        for uri in (spec.base_color_uri, spec.normal_uri, spec.orm_uri):
            path = root / uri
            if not path.is_file():
                raise FileNotFoundError(path)

    document, binary = compile_skinned_multi_gltf(
        primitives,
        skeleton,
        animations,
        name=name,
        buffer_uri=binary_name,
    )
    (root / binary_name).write_bytes(binary)
    gltf_bytes = (json.dumps(document, indent=2, sort_keys=True) + "\n").encode("utf-8")
    (root / gltf_name).write_bytes(gltf_bytes)
    report = validate_gltf(document, binary, root)
    if report["status"] != "pass":
        raise ValueError(f"skinned multi-material glTF failed validation: {report}")
    return {
        "gltf": gltf_name,
        "binary": binary_name,
        "gltf_sha256": _sha256(gltf_bytes),
        "binary_sha256": _sha256(binary),
        "validation": report,
        "primitive_count": len(primitives),
        "material_count": len(primitives),
        "triangles": document["extras"]["axm"]["triangles"],
        "compiled_vertices": document["extras"]["axm"]["compiled_vertices"],
        "joints": len(skeleton.joints),
        "animations": [clip.name for clip in animations],
        "material_names": [spec.material_name for spec in primitives],
    }
