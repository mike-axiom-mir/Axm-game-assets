#!/usr/bin/env python3
"""AXM native skinned + morph-capable glTF 2.0 compiler v0.2."""
from __future__ import annotations

import json
import math
import struct
from pathlib import Path
from typing import Any, Sequence

from native_animation import AnimationClip, validate_animation_clip
from native_geometry import Mesh, vertex_normals
from native_gltf import _add_view, _align4, _pack_vec, _sha256, _tangents, validate_gltf
from native_morph import MorphTarget, validate_morph_set
from native_skin import (
    Skeleton,
    SkinWeights,
    flatten_matrix_column_major,
    inverse_bind_matrices,
    validate_skeleton,
    validate_skin_weights,
)
from native_uv import UVMap, validate_uv


def _expanded(mesh: Mesh, uvmap: UVMap):
    uv_report = validate_uv(mesh, uvmap)
    if uv_report["status"] != "pass":
        raise ValueError(f"invalid UV state: {uv_report}")
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
                vi = face[local]
                ui = uvface[local]
                positions.append(mesh.vertices[vi])
                expanded_normals.append(normals[vi])
                texcoords.append(uvmap.uvs[ui])
                source_indices.append(vi)
                indices.append(len(indices))
    return positions, expanded_normals, texcoords, indices, source_indices


def _pack_u16_vec4(values: Sequence[tuple[int, int, int, int]]) -> bytes:
    flat = [component for row in values for component in row]
    if any(value < 0 or value > 65535 for value in flat):
        raise ValueError("joint index exceeds unsigned-short glTF storage")
    return struct.pack("<" + "H" * len(flat), *flat)


def _normalized_vec3(value: tuple[float, float, float]) -> tuple[float, float, float]:
    length = math.sqrt(value[0] * value[0] + value[1] * value[1] + value[2] * value[2])
    if length <= 1e-12:
        raise ValueError("cannot normalize near-zero morph normal")
    return (value[0] / length, value[1] / length, value[2] / length)


def compile_character_gltf(
    mesh: Mesh,
    uvmap: UVMap,
    skeleton: Skeleton,
    skin_weights: SkinWeights,
    morph_targets: Sequence[MorphTarget],
    animations: Sequence[AnimationClip] = (),
    *,
    buffer_uri: str,
    base_color_uri: str,
    normal_uri: str,
    orm_uri: str,
) -> tuple[dict[str, Any], bytes]:
    skeleton_report = validate_skeleton(skeleton)
    if skeleton_report["status"] != "pass":
        raise ValueError(f"invalid skeleton: {skeleton_report}")
    skin_report = validate_skin_weights(skin_weights, vertex_count=len(mesh.vertices), joint_count=len(skeleton.joints))
    if skin_report["status"] != "pass":
        raise ValueError(f"invalid skin weights: {skin_report}")
    morph_report = validate_morph_set(morph_targets, vertex_count=len(mesh.vertices))
    if morph_report["status"] != "pass":
        raise ValueError(f"invalid morph targets: {morph_report}")
    for clip in animations:
        animation_report = validate_animation_clip(clip, skeleton)
        if animation_report["status"] != "pass":
            raise ValueError(f"invalid animation {clip.name}: {animation_report}")

    positions, normals, texcoords, indices, source_indices = _expanded(mesh, uvmap)
    if not positions:
        raise ValueError("mesh produced no triangles")
    tangents = _tangents(positions, normals, texcoords)
    expanded_joints = [skin_weights.joints[index] for index in source_indices]
    expanded_weights = [skin_weights.weights[index] for index in source_indices]

    blob = bytearray()
    views: list[dict[str, Any]] = []
    accessors: list[dict[str, Any]] = []

    def add_float(values, gltf_type: str, component_count: int, *, target: int | None = 34962, include_bounds: bool = False):
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

    inverse_binds = [flatten_matrix_column_major(matrix) for matrix in inverse_bind_matrices(skeleton)]
    inverse_bind_accessor = add_float(inverse_binds, "MAT4", 16, target=None)

    # glTF morph TANGENT attributes are VEC3 deltas: tangent handedness (the
    # base VEC4.w sign) is not morphed. Derive them in expanded UV-corner space
    # rather than source-vertex space so seams keep their own tangent basis.
    # If the recomputed basis chooses the equivalent opposite handedness, flip
    # its tangent XYZ too; keeping base w with -T preserves the same bitangent.
    morph_entries: list[dict[str, int]] = []
    morph_tangent_targets = 0
    morph_tangent_reoriented_corners = 0
    for target in morph_targets:
        entry: dict[str, int] = {}
        position_deltas = [target.position_deltas[index] for index in source_indices]
        entry["POSITION"] = add_float(position_deltas, "VEC3", 3)
        if target.normal_deltas is not None:
            normal_deltas = [target.normal_deltas[index] for index in source_indices]
            entry["NORMAL"] = add_float(normal_deltas, "VEC3", 3)

            deformed_positions = [
                (
                    base[0] + delta[0],
                    base[1] + delta[1],
                    base[2] + delta[2],
                )
                for base, delta in zip(positions, position_deltas)
            ]
            deformed_normals = [
                _normalized_vec3((
                    base[0] + delta[0],
                    base[1] + delta[1],
                    base[2] + delta[2],
                ))
                for base, delta in zip(normals, normal_deltas)
            ]
            deformed_tangents = _tangents(deformed_positions, deformed_normals, texcoords)
            tangent_deltas: list[tuple[float, float, float]] = []
            for base_tangent, deformed_tangent in zip(tangents, deformed_tangents):
                orientation = 1.0
                if base_tangent[3] * deformed_tangent[3] < 0.0:
                    orientation = -1.0
                    morph_tangent_reoriented_corners += 1
                aligned_tangent = (
                    deformed_tangent[0] * orientation,
                    deformed_tangent[1] * orientation,
                    deformed_tangent[2] * orientation,
                )
                tangent_deltas.append((
                    aligned_tangent[0] - base_tangent[0],
                    aligned_tangent[1] - base_tangent[1],
                    aligned_tangent[2] - base_tangent[2],
                ))
            entry["TANGENT"] = add_float(tangent_deltas, "VEC3", 3)
            morph_tangent_targets += 1
        morph_entries.append(entry)

    animation_entries: list[dict[str, Any]] = []
    path_types = {"translation": ("VEC3", 3), "rotation": ("VEC4", 4), "scale": ("VEC3", 3)}
    for clip in animations:
        samplers: list[dict[str, Any]] = []
        channels: list[dict[str, Any]] = []
        for track in clip.tracks:
            input_values = [(float(time),) for time in track.times]
            input_accessor = add_float(input_values, "SCALAR", 1, target=None, include_bounds=True)
            output_type, output_width = path_types[track.path]
            output_values = [tuple(float(component) for component in value) for value in track.values]
            output_accessor = add_float(output_values, output_type, output_width, target=None)
            sampler_index = len(samplers)
            samplers.append({"input": input_accessor, "output": output_accessor, "interpolation": track.interpolation})
            channels.append({"sampler": sampler_index, "target": {"node": track.joint + 1, "path": track.path}})
        animation_entries.append({"name": clip.name, "samplers": samplers, "channels": channels})

    _align4(blob)

    mesh_node: dict[str, Any] = {"name": mesh.name, "mesh": 0, "skin": 0}
    nodes: list[dict[str, Any]] = [mesh_node]
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
    root_joint = skeleton_report["roots"][0]

    primitive: dict[str, Any] = {
        "attributes": {
            "POSITION": position_accessor,
            "NORMAL": normal_accessor,
            "TEXCOORD_0": uv_accessor,
            "TANGENT": tangent_accessor,
            "JOINTS_0": joints_accessor,
            "WEIGHTS_0": weights_accessor,
        },
        "indices": index_accessor,
        "material": 0,
        "mode": 4,
    }
    if morph_entries:
        primitive["targets"] = morph_entries

    mesh_entry: dict[str, Any] = {"name": mesh.name, "primitives": [primitive]}
    if morph_targets:
        mesh_entry["weights"] = [0.0] * len(morph_targets)
        mesh_entry["extras"] = {"targetNames": [target.name for target in morph_targets]}

    document: dict[str, Any] = {
        "asset": {"version": "2.0", "generator": "AXM Game Asset Forge native_character_gltf v0.2"},
        "scene": 0,
        "scenes": [{"nodes": [0, int(root_joint) + 1]}],
        "nodes": nodes,
        "meshes": [mesh_entry],
        "skins": [{
            "name": f"{mesh.name}_skin",
            "inverseBindMatrices": inverse_bind_accessor,
            "joints": [index + 1 for index in range(len(skeleton.joints))],
            "skeleton": int(root_joint) + 1,
        }],
        "buffers": [{"uri": buffer_uri, "byteLength": len(blob)}],
        "bufferViews": views,
        "accessors": accessors,
        "samplers": [{"magFilter": 9729, "minFilter": 9987, "wrapS": 10497, "wrapT": 10497}],
        "images": [{"uri": base_color_uri}, {"uri": orm_uri}, {"uri": normal_uri}],
        "textures": [{"sampler": 0, "source": 0}, {"sampler": 0, "source": 1}, {"sampler": 0, "source": 2}],
        "materials": [{
            "name": "AXM_Native_Character_Material",
            "pbrMetallicRoughness": {
                "baseColorTexture": {"index": 0},
                "metallicRoughnessTexture": {"index": 1},
                "metallicFactor": 1.0,
                "roughnessFactor": 1.0,
            },
            "normalTexture": {"index": 2},
            "occlusionTexture": {"index": 1},
        }],
        "animations": animation_entries,
        "extras": {
            "axm": {
                "compiler": "native_character_gltf",
                "source_vertices": len(mesh.vertices),
                "compiled_vertices": len(positions),
                "triangles": len(indices) // 3,
                "joints": len(skeleton.joints),
                "morph_targets": len(morph_targets),
                "morph_tangent_targets": morph_tangent_targets,
                "morph_tangent_reoriented_corners": morph_tangent_reoriented_corners,
                "animations": len(animations),
                "truth": "Native structural character compiler with skeletal animation delivery. Morph targets that provide normal deltas also derive tangent deltas per expanded UV corner so normal-mapped deformation keeps a coherent tangent basis. Equivalent tangent bases whose recomputed handedness flips are represented by negating tangent XYZ while retaining the immutable base handedness sign. Rig-generation intelligence, animation synthesis, correctives, hair/cloth and engine deformation evidence remain separate gates.",
            }
        },
    }
    return document, bytes(blob)


def write_character_gltf(
    mesh: Mesh,
    uvmap: UVMap,
    skeleton: Skeleton,
    skin_weights: SkinWeights,
    morph_targets: Sequence[MorphTarget],
    output: str | Path,
    animations: Sequence[AnimationClip] = (),
    *,
    texture_dir: str = "textures",
) -> dict[str, Any]:
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
    document, binary = compile_character_gltf(
        mesh,
        uvmap,
        skeleton,
        skin_weights,
        morph_targets,
        animations,
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
        raise ValueError(f"character glTF failed internal structural validation: {report}")
    return {
        "gltf": gltf_name,
        "binary": binary_name,
        "gltf_sha256": _sha256(gltf_bytes),
        "binary_sha256": _sha256(binary),
        "validation": report,
        "triangles": document["extras"]["axm"]["triangles"],
        "compiled_vertices": document["extras"]["axm"]["compiled_vertices"],
        "joints": len(skeleton.joints),
        "morph_targets": len(morph_targets),
        "morph_tangent_targets": document["extras"]["axm"]["morph_tangent_targets"],
        "morph_tangent_reoriented_corners": document["extras"]["axm"]["morph_tangent_reoriented_corners"],
        "animations": len(animations),
    }
