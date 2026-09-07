#!/usr/bin/env python3
"""AXM morph-weight facial animation layer for native character glTF v0.1."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Sequence

from native_animation import AnimationClip
from native_character_gltf import compile_character_gltf
from native_facial import MorphWeightClip, validate_morph_weight_clip
from native_geometry import Mesh
from native_gltf import _add_view, _align4, _pack_vec, _sha256, validate_gltf
from native_morph import MorphTarget
from native_skin import Skeleton, SkinWeights
from native_uv import UVMap


def compile_facial_character_gltf(
    mesh: Mesh,
    uvmap: UVMap,
    skeleton: Skeleton,
    skin_weights: SkinWeights,
    morph_targets: Sequence[MorphTarget],
    skeletal_animations: Sequence[AnimationClip] = (),
    morph_animations: Sequence[MorphWeightClip] = (),
    *,
    buffer_uri: str,
    base_color_uri: str,
    normal_uri: str,
    orm_uri: str,
) -> tuple[dict[str, Any], bytes]:
    document, binary = compile_character_gltf(
        mesh,
        uvmap,
        skeleton,
        skin_weights,
        morph_targets,
        skeletal_animations,
        buffer_uri=buffer_uri,
        base_color_uri=base_color_uri,
        normal_uri=normal_uri,
        orm_uri=orm_uri,
    )
    morph_count = len(morph_targets)
    for clip in morph_animations:
        report = validate_morph_weight_clip(clip, morph_count)
        if report["status"] != "pass":
            raise ValueError(f"invalid morph animation {clip.name}: {report}")

    blob = bytearray(binary)
    views = document["bufferViews"]
    accessors = document["accessors"]
    animation_entries = document.setdefault("animations", [])
    existing_names = {entry.get("name") for entry in animation_entries}

    for clip in morph_animations:
        if clip.name in existing_names:
            raise ValueError(f"animation name {clip.name!r} already exists")
        input_values = [(float(time),) for time in clip.times]
        input_view = _add_view(blob, _pack_vec(input_values), views, target=None)
        accessors.append({
            "bufferView": input_view,
            "byteOffset": 0,
            "componentType": 5126,
            "count": len(input_values),
            "type": "SCALAR",
            "min": [min(clip.times)],
            "max": [max(clip.times)],
        })
        input_accessor = len(accessors) - 1

        flattened = [(float(weight),) for row in clip.values for weight in row]
        output_view = _add_view(blob, _pack_vec(flattened), views, target=None)
        accessors.append({
            "bufferView": output_view,
            "byteOffset": 0,
            "componentType": 5126,
            "count": len(flattened),
            "type": "SCALAR",
        })
        output_accessor = len(accessors) - 1
        animation_entries.append({
            "name": clip.name,
            "samplers": [{
                "input": input_accessor,
                "output": output_accessor,
                "interpolation": clip.interpolation,
            }],
            "channels": [{
                "sampler": 0,
                "target": {"node": 0, "path": "weights"},
            }],
            "extras": {
                "axm_morph_count": morph_count,
                "axm_key_count": len(clip.times),
            },
        })
        existing_names.add(clip.name)

    _align4(blob)
    document["buffers"][0]["byteLength"] = len(blob)
    document["asset"]["generator"] = "AXM Game Asset Forge native_facial_gltf v0.1"
    axm = document.setdefault("extras", {}).setdefault("axm", {})
    axm["facial_weight_animations"] = len(morph_animations)
    axm["truth"] = (
        "Native structural character delivery with skeletal and morph-weight animation channels. "
        "Corrective quality, facial anatomy, wrinkles, eye/teeth integration and engine close-up evidence remain separate gates."
    )
    return document, bytes(blob)


def write_facial_character_gltf(
    mesh: Mesh,
    uvmap: UVMap,
    skeleton: Skeleton,
    skin_weights: SkinWeights,
    morph_targets: Sequence[MorphTarget],
    output: str | Path,
    skeletal_animations: Sequence[AnimationClip] = (),
    morph_animations: Sequence[MorphWeightClip] = (),
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

    document, binary = compile_facial_character_gltf(
        mesh,
        uvmap,
        skeleton,
        skin_weights,
        morph_targets,
        skeletal_animations,
        morph_animations,
        buffer_uri=binary_name,
        base_color_uri=base_uri,
        normal_uri=normal_uri,
        orm_uri=orm_uri,
    )
    (root / binary_name).write_bytes(binary)
    gltf_bytes = (json.dumps(document, indent=2, sort_keys=True) + "\n").encode("utf-8")
    (root / gltf_name).write_bytes(gltf_bytes)
    report = validate_gltf(document, binary, root)
    if report["status"] != "pass":
        raise ValueError(f"facial character glTF failed structural validation: {report}")
    weight_channels = sum(
        1
        for animation in document.get("animations", [])
        for channel in animation.get("channels", [])
        if channel.get("target", {}).get("path") == "weights"
    )
    return {
        "gltf": gltf_name,
        "binary": binary_name,
        "gltf_sha256": _sha256(gltf_bytes),
        "binary_sha256": _sha256(binary),
        "validation": report,
        "triangles": document["extras"]["axm"]["triangles"],
        "joints": len(skeleton.joints),
        "morph_targets": len(morph_targets),
        "skeletal_animations": len(skeletal_animations),
        "morph_animations": len(morph_animations),
        "weight_channels": weight_channels,
    }
