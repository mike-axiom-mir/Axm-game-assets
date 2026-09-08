#!/usr/bin/env python3
"""Source-grounded finger extension for the shared hm08 humanoid rig.

The existing 23-joint body rig remains canonical. This module consumes the
pinned ``hm08_finger_landmarks_v0.1`` packet and appends 15 phalanx pivots per
hand (3 segments x 5 digits), producing a 53-joint skeleton. Finger surface
weights are derived from distance/projection along the pinned source bone
segments and override only finger neighborhoods; all other weights are copied
byte-for-byte from the promoted bone-segment humanoid skin v0.2.
"""
from __future__ import annotations

import hashlib
import json
from math import sqrt
from pathlib import Path

from native_geometry import Mesh, Vec3, bounds
from native_hm08_humanoid_rig import build_hm08_humanoid_skeleton, derive_hm08_rig_landmarks
from native_hm08_humanoid_skin_v2 import build_hm08_skin_weights_v2
from native_skin import (
    Joint,
    Skeleton,
    SkinWeights,
    global_joint_matrices,
    skin_vertices,
    transform_point,
    validate_skeleton,
    validate_skin_weights,
)

SCHEMA = "axm.game-assets.hm08-finger-rig.v0.1"
SKIN_SCHEMA = "axm.game-assets.hm08-finger-skin.v0.1"
FINGER_SEED = Path("seed_data/hm08_finger_landmarks_v0.1/finger-landmarks.json")


def _sub(a: Vec3, b: Vec3) -> Vec3:
    return a[0]-b[0], a[1]-b[1], a[2]-b[2]


def _add(a: Vec3, b: Vec3) -> Vec3:
    return a[0]+b[0], a[1]+b[1], a[2]+b[2]


def _mul(a: Vec3, scalar: float) -> Vec3:
    return a[0]*scalar, a[1]*scalar, a[2]*scalar


def _dot(a: Vec3, b: Vec3) -> float:
    return a[0]*b[0] + a[1]*b[1] + a[2]*b[2]


def _length(a: Vec3) -> float:
    return sqrt(_dot(a, a))


def _distance(a: Vec3, b: Vec3) -> float:
    return _length(_sub(a, b))


def _segment_distance(point: Vec3, start: Vec3, end: Vec3) -> tuple[float, float]:
    axis = _sub(end, start)
    denom = max(_dot(axis, axis), 1e-12)
    t = max(0.0, min(1.0, _dot(_sub(point, start), axis) / denom))
    nearest = _add(start, _mul(axis, t))
    return _distance(point, nearest), t


def _smooth01(value: float) -> float:
    t = max(0.0, min(1.0, value))
    return t*t*(3.0-2.0*t)


def _row(*pairs: tuple[int, float]) -> tuple[tuple[int,int,int,int], tuple[float,float,float,float]]:
    merged: dict[int, float] = {}
    for joint, weight in pairs:
        if weight > 1e-12:
            merged[joint] = merged.get(joint, 0.0) + float(weight)
    ordered = sorted(merged.items(), key=lambda item: (-item[1], item[0]))[:4]
    total = sum(weight for _joint, weight in ordered)
    if total <= 1e-12:
        raise ValueError("finger weight row has zero total")
    ordered = [(joint, weight/total) for joint, weight in ordered]
    while len(ordered) < 4:
        ordered.append((0, 0.0))
    return tuple(joint for joint, _weight in ordered), tuple(weight for _joint, weight in ordered)


def _packet_sha(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def load_finger_landmarks(path: str | Path = FINGER_SEED) -> dict[str, object]:
    source = Path(path)
    packet = json.loads(source.read_text(encoding="utf-8"))
    if packet.get("schema") != "axm.game-assets.hm08-finger-landmarks.v0.1":
        raise ValueError("unexpected hm08 finger landmark schema")
    if int(packet.get("finger_bone_count", 0)) != 30 or packet.get("side_counts") != {"L":15,"R":15}:
        raise ValueError("hm08 finger landmark packet is incomplete")
    if not all(packet.get("acceptance", {}).values()):
        raise ValueError(f"hm08 finger landmark packet is not green: {packet.get('acceptance')}")
    packet = dict(packet)
    packet["file_sha256"] = _packet_sha(source)
    return packet


def _source_side_mapping(packet: dict[str, object]) -> dict[str, str]:
    means: dict[str, float] = {}
    rows = packet["bones"]
    assert isinstance(rows, list)
    for label in ("L", "R"):
        xs = [
            (float(row["head_m"][0]) + float(row["tail_m"][0])) * 0.5
            for row in rows if row["side"] == label
        ]
        if not xs:
            raise ValueError(f"source finger side {label} is empty")
        means[label] = sum(xs) / len(xs)
    if means["L"] * means["R"] >= 0.0:
        raise ValueError(f"source finger sides do not straddle body center: {means}")
    negative = min(means, key=means.get)
    positive = max(means, key=means.get)
    # Forge body convention used throughout this repo: left is -X, right is +X.
    return {"left": negative, "right": positive}


def _finger_rows(packet: dict[str, object], mapping: dict[str, str]) -> dict[tuple[str,int,int], dict[str, object]]:
    result: dict[tuple[str,int,int], dict[str, object]] = {}
    rows = packet["bones"]
    assert isinstance(rows, list)
    inverse = {source: forge for forge, source in mapping.items()}
    for row in rows:
        source_side = str(row["side"])
        if source_side not in inverse:
            continue
        key = (inverse[source_side], int(row["digit"]), int(row["segment"]))
        result[key] = row
    expected = {(side,digit,segment) for side in ("left","right") for digit in range(1,6) for segment in range(1,4)}
    if set(result) != expected:
        raise ValueError(f"finger landmark map incomplete: missing={sorted(expected-set(result))}")
    return result


def build_hm08_finger_skeleton(
    body: Mesh,
    *,
    landmark_path: str | Path = FINGER_SEED,
) -> tuple[Skeleton, dict[str, int], dict[str, object]]:
    packet = load_finger_landmarks(landmark_path)
    mapping = _source_side_mapping(packet)
    rows = _finger_rows(packet, mapping)
    base, base_evidence, indices = build_hm08_humanoid_skeleton(body)
    base_globals = global_joint_matrices(base)
    joints = list(base.joints)
    finger_indices: dict[str, int] = {}
    tip_offsets: dict[str, list[float]] = {}
    continuity_gaps: list[float] = []
    source_lengths: list[float] = []

    for side in ("left", "right"):
        hand_index = indices[f"{side}_hand"]
        hand_world = transform_point(base_globals[hand_index], (0.0,0.0,0.0))
        for digit in range(1, 6):
            parent_index = hand_index
            parent_world = hand_world
            previous_tail: Vec3 | None = None
            for segment in range(1, 4):
                row = rows[(side,digit,segment)]
                head = tuple(float(value) for value in row["head_m"])  # type: ignore[assignment]
                tail = tuple(float(value) for value in row["tail_m"])  # type: ignore[assignment]
                name = f"{side}_finger{digit}_{segment}"
                local_translation = _sub(head, parent_world)
                finger_indices[name] = len(joints)
                joints.append(Joint(name, parent=parent_index, translation=local_translation))
                if previous_tail is not None:
                    continuity_gaps.append(_distance(previous_tail, head))
                source_lengths.append(_distance(head, tail))
                previous_tail = tail
                parent_index = finger_indices[name]
                parent_world = head
                if segment == 3:
                    tip_offsets[f"{side}_finger{digit}_tip"] = list(_sub(tail, head))

    skeleton = Skeleton(joints)
    validation = validate_skeleton(skeleton)
    if validation["status"] != "pass":
        raise ValueError(f"hm08 finger skeleton invalid: {validation}")
    globals_ = global_joint_matrices(skeleton)
    pivot_errors: list[float] = []
    tip_errors: list[float] = []
    for side in ("left","right"):
        for digit in range(1,6):
            for segment in range(1,4):
                row = rows[(side,digit,segment)]
                expected_head = tuple(float(value) for value in row["head_m"])
                index = finger_indices[f"{side}_finger{digit}_{segment}"]
                actual_head = transform_point(globals_[index], (0.0,0.0,0.0))
                pivot_errors.append(_distance(expected_head, actual_head))
                if segment == 3:
                    expected_tip = tuple(float(value) for value in row["tail_m"])
                    local_tip = tuple(float(value) for value in tip_offsets[f"{side}_finger{digit}_tip"])
                    actual_tip = transform_point(globals_[index], local_tip)
                    tip_errors.append(_distance(expected_tip, actual_tip))

    evidence: dict[str, object] = {
        "schema": SCHEMA,
        "base_rig_schema": base_evidence["schema"],
        "base_joint_count": len(base.joints),
        "finger_joint_count": len(finger_indices),
        "total_joint_count": len(skeleton.joints),
        "source_side_mapping": mapping,
        "source_packet_sha256": packet["file_sha256"],
        "source_revision": packet["source"]["makehuman_revision"],
        "source_rig_blob_sha1": packet["source"]["default_mhskel_git_blob_sha1"],
        "finger_indices": finger_indices,
        "tip_local_offsets": tip_offsets,
        "source_chain_continuity_gap_m": {
            "max": max(continuity_gaps) if continuity_gaps else 0.0,
            "mean": sum(continuity_gaps)/len(continuity_gaps) if continuity_gaps else 0.0,
        },
        "source_bone_length_m": {
            "min": min(source_lengths),
            "max": max(source_lengths),
        },
        "bind_source_pivot_error_m": max(pivot_errors),
        "bind_source_tip_error_m": max(tip_errors),
        "skeleton_validation": validation,
        "truth": {
            "shared_23_joint_rig_preserved": True,
            "source_grounded": True,
            "application_code_imported": False,
            "production_finger_rig_claim": False,
            "notes": [
                "The 30 appended pivots come from the pinned MakeHuman default.mhskel landmark packet; Forge owns this skeleton construction and all later pose/weight logic.",
                "First phalanx pivots parent directly to the shared anatomical hand joint. Segments two and three parent to the previous source-grounded phalanx pivot.",
                "Distal tips are retained as local offsets rather than extra joints, keeping the shared rig at 53 joints while preserving source fingertip markers."
            ],
        },
    }
    return skeleton, finger_indices, evidence


def build_hm08_finger_skin_weights(
    body: Mesh,
    skeleton: Skeleton,
    finger_indices: dict[str, int],
    *,
    landmark_path: str | Path = FINGER_SEED,
) -> tuple[SkinWeights, dict[str, object]]:
    packet = load_finger_landmarks(landmark_path)
    mapping = _source_side_mapping(packet)
    rows = _finger_rows(packet, mapping)
    landmarks = derive_hm08_rig_landmarks(body)
    base_skeleton, _base_rig_evidence, base_indices = build_hm08_humanoid_skeleton(body)
    base_weights, base_skin_evidence = build_hm08_skin_weights_v2(body, base_skeleton, landmarks, base_indices)
    joints = [tuple(row) for row in base_weights.joints]
    weights = [tuple(row) for row in base_weights.weights]

    lo, hi = bounds(body)
    half_width = max(abs(lo[0]), abs(hi[0]), 1e-9)
    segment_rows: dict[str, tuple[Vec3,Vec3,float,int,int,int|None]] = {}
    for side in ("left","right"):
        for digit in range(1,6):
            for segment in range(1,4):
                row = rows[(side,digit,segment)]
                head = tuple(float(value) for value in row["head_m"])  # type: ignore[assignment]
                tail = tuple(float(value) for value in row["tail_m"])  # type: ignore[assignment]
                length = _distance(head, tail)
                radius = max(0.0085, min(0.0185, length*0.42 + 0.0035))
                current = finger_indices[f"{side}_finger{digit}_{segment}"]
                parent = base_indices[f"{side}_hand"] if segment == 1 else finger_indices[f"{side}_finger{digit}_{segment-1}"]
                child = finger_indices[f"{side}_finger{digit}_{segment+1}"] if segment < 3 else None
                segment_rows[f"{side}:{digit}:{segment}"] = (head,tail,radius,current,parent,child)

    overridden: set[int] = set()
    assigned_by_segment = {key: 0 for key in segment_rows}
    assigned_by_side = {"left":0,"right":0}
    normalized_distance_max = 0.0
    for vertex_index, point in enumerate(body.vertices):
        # Full body is in a T/A-pose with fingers at the lateral extremes. This
        # keeps palm/torso/arm surfaces out of the finger classifier.
        if abs(point[0]) < half_width*0.77:
            continue
        side = "left" if point[0] < 0.0 else "right"
        candidates = []
        for digit in range(1,6):
            for segment in range(1,4):
                key = f"{side}:{digit}:{segment}"
                head,tail,radius,current,parent,child = segment_rows[key]
                distance,t = _segment_distance(point,head,tail)
                candidates.append((distance/radius,distance,t,key,current,parent,child))
        normalized,distance,t,key,current,parent,child = min(candidates, key=lambda row:(row[0],row[3]))
        if normalized > 1.32:
            continue
        if t < 0.22:
            blend = _smooth01(t/0.22)
            joint_row, weight_row = _row((parent,1.0-blend),(current,blend))
        elif child is not None and t > 0.78:
            blend = _smooth01((t-0.78)/0.22)
            joint_row, weight_row = _row((current,1.0-blend),(child,blend))
        else:
            joint_row, weight_row = _row((current,1.0))
        joints[vertex_index] = joint_row
        weights[vertex_index] = weight_row
        overridden.add(vertex_index)
        assigned_by_segment[key] += 1
        assigned_by_side[side] += 1
        normalized_distance_max = max(normalized_distance_max, normalized)

    result = SkinWeights(joints, weights)
    validation = validate_skin_weights(result, vertex_count=len(body.vertices), joint_count=len(skeleton.joints))
    if validation["status"] != "pass":
        raise ValueError(f"hm08 finger skin invalid: {validation}")
    uninfluenced_segments = sorted(key for key, count in assigned_by_segment.items() if count == 0)
    if uninfluenced_segments:
        raise ValueError(f"finger segments received no surface vertices: {uninfluenced_segments}")
    preserved_rows = sum(
        1 for index in range(len(body.vertices))
        if index not in overridden and joints[index] == base_weights.joints[index] and weights[index] == base_weights.weights[index]
    )
    bind_vertices = skin_vertices(body, result, skeleton, skeleton)
    bind_error = max(_distance(before, after) for before, after in zip(body.vertices, bind_vertices))
    active_counts = [sum(1 for value in row if value > 1e-8) for row in weights]

    evidence: dict[str, object] = {
        "schema": SKIN_SCHEMA,
        "base_skin_schema": base_skin_evidence["schema"],
        "vertex_count": len(body.vertices),
        "joint_count": len(skeleton.joints),
        "overridden_finger_vertices": len(overridden),
        "assigned_by_side": assigned_by_side,
        "assigned_by_segment": assigned_by_segment,
        "minimum_vertices_per_segment": min(assigned_by_segment.values()),
        "normalized_segment_distance_max": normalized_distance_max,
        "preserved_nonfinger_rows": preserved_rows,
        "expected_preserved_nonfinger_rows": len(body.vertices)-len(overridden),
        "bind_reconstruction_max_error_m": bind_error,
        "max_influences": max(active_counts),
        "mean_influences": sum(active_counts)/len(active_counts),
        "validation": validation,
        "truth": {
            "shared_body_skin_preserved_outside_fingers": preserved_rows == len(body.vertices)-len(overridden),
            "source_grounded_segments": True,
            "production_finger_skinning_claim": False,
            "corrective_shapes_claim": False,
            "notes": [
                "Only lateral finger neighborhoods near pinned source bone segments are reweighted. Palm, wrist, arm, torso, head and lower body retain the promoted humanoid skin v0.2 rows exactly.",
                "Each finger segment is rigid through its midsection with bounded parent/current and current/child blends at source-grounded joints.",
                "Production quality still depends on grip-pose evidence, glove binding and corrective shapes at compressed knuckles."
            ],
        },
    }
    return result, evidence


def build_preferred_hm08_finger_rig():
    from native_hm08_undersuit import _load_identity_body
    body, _uv, _state = _load_identity_body()
    skeleton, indices, rig_evidence = build_hm08_finger_skeleton(body)
    weights, skin_evidence = build_hm08_finger_skin_weights(body, skeleton, indices)
    return body, skeleton, weights, indices, {"rig":rig_evidence,"skin":skin_evidence}


if __name__ == "__main__":
    import json
    body, skeleton, _weights, _indices, evidence = build_preferred_hm08_finger_rig()
    print(json.dumps({"vertices":len(body.vertices),"joints":len(skeleton.joints),**evidence},indent=2))
