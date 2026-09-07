#!/usr/bin/env python3
"""Machine-readable AXM native character state packet v0.1."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from native_animation import AnimationClip, AnimationTrack, contact_drift, validate_animation_clip
from native_geometry import Mesh
from native_morph import MorphTarget, validate_morph_set
from native_skin import Joint, Skeleton, SkinWeights, validate_skeleton, validate_skin_weights

SCHEMA = "axm.game-assets.character-state.v0.1"


@dataclass(slots=True)
class CharacterState:
    asset_id: str
    skeleton: Skeleton
    skin: SkinWeights
    morph_targets: list[MorphTarget]
    animations: list[AnimationClip]
    contacts: list[dict[str, Any]]
    provenance: dict[str, Any]


def _vec(value, width: int, label: str):
    if not isinstance(value, list) or len(value) != width:
        raise ValueError(f"{label} must contain {width} values")
    return tuple(value)


def from_dict(data: dict[str, Any]) -> CharacterState:
    if data.get("schema") != SCHEMA:
        raise ValueError(f"unsupported character-state schema {data.get('schema')}")
    asset_id = str(data.get("asset_id", "")).strip()
    if not asset_id:
        raise ValueError("asset_id is required")

    joints = []
    for index, item in enumerate(data.get("skeleton", {}).get("joints", [])):
        joints.append(Joint(
            name=str(item.get("name", "")),
            parent=item.get("parent"),
            translation=_vec(item.get("translation", [0.0, 0.0, 0.0]), 3, f"joint {index} translation"),
            rotation=_vec(item.get("rotation", [0.0, 0.0, 0.0, 1.0]), 4, f"joint {index} rotation"),
            scale=_vec(item.get("scale", [1.0, 1.0, 1.0]), 3, f"joint {index} scale"),
        ))
    skeleton = Skeleton(joints)

    skin_data = data.get("skin", {})
    skin = SkinWeights(
        joints=[_vec(row, 4, f"skin joints row {index}") for index, row in enumerate(skin_data.get("joints", []))],
        weights=[_vec(row, 4, f"skin weights row {index}") for index, row in enumerate(skin_data.get("weights", []))],
    )

    morphs = []
    for item in data.get("morph_targets", []):
        normals = item.get("normal_deltas")
        morphs.append(MorphTarget(
            name=str(item.get("name", "")),
            position_deltas=[_vec(row, 3, f"morph {item.get('name')} position delta") for row in item.get("position_deltas", [])],
            normal_deltas=None if normals is None else [_vec(row, 3, f"morph {item.get('name')} normal delta") for row in normals],
        ))

    animations = []
    for clip in data.get("animations", []):
        tracks = []
        for track in clip.get("tracks", []):
            tracks.append(AnimationTrack(
                joint=int(track.get("joint", -1)),
                path=str(track.get("path", "")),
                times=[float(value) for value in track.get("times", [])],
                values=[tuple(value) for value in track.get("values", [])],
                interpolation=str(track.get("interpolation", "LINEAR")),
            ))
        animations.append(AnimationClip(str(clip.get("name", "")), tracks))

    contacts = list(data.get("contacts", []))
    provenance = dict(data.get("provenance", {}))
    return CharacterState(asset_id, skeleton, skin, morphs, animations, contacts, provenance)


def audit_character_state(state: CharacterState, mesh: Mesh) -> dict[str, Any]:
    gates: list[dict[str, Any]] = []

    def gate(name: str, report: dict[str, Any]):
        gates.append({"gate": name, **report})

    gate("skeleton", validate_skeleton(state.skeleton))
    gate("skin_weights", validate_skin_weights(state.skin, vertex_count=len(mesh.vertices), joint_count=len(state.skeleton.joints)))
    gate("morphs", validate_morph_set(state.morph_targets, vertex_count=len(mesh.vertices)))

    animations_by_name = {clip.name: clip for clip in state.animations}
    if len(animations_by_name) != len(state.animations):
        gates.append({"gate": "animation_names", "status": "fail", "failures": ["animation names must be unique"]})
    for clip in state.animations:
        gate(f"animation:{clip.name}", validate_animation_clip(clip, state.skeleton))

    for contact in state.contacts:
        name = str(contact.get("id", "unnamed"))
        clip_name = str(contact.get("animation", ""))
        clip = animations_by_name.get(clip_name)
        if clip is None:
            gates.append({"gate": f"contact:{name}", "status": "fail", "failures": [f"animation {clip_name!r} not found"]})
            continue
        try:
            evidence = contact_drift(
                mesh,
                state.skin,
                state.skeleton,
                clip,
                [int(value) for value in contact.get("vertices", [])],
                [float(value) for value in contact.get("sample_times", [])],
            )
        except (ValueError, TypeError) as exc:
            gates.append({"gate": f"contact:{name}", "status": "fail", "failures": [str(exc)]})
            continue
        threshold = float(contact.get("max_drift", 0.01))
        status = "pass" if evidence["max_drift"] <= threshold else "fail"
        gates.append({"gate": f"contact:{name}", "status": status, "threshold": threshold, "evidence": evidence, "failures": [] if status == "pass" else [f"drift {evidence['max_drift']:.9g} exceeds {threshold:.9g}"]})

    failures = [gate for gate in gates if gate.get("status") != "pass"]
    return {
        "status": "pass" if not failures else "fail",
        "asset_id": state.asset_id,
        "gates": gates,
        "counts": {"pass": sum(g.get("status") == "pass" for g in gates), "fail": len(failures)},
    }
