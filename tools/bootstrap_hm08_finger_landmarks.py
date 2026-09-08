#!/usr/bin/env python3
"""Derive source-indexed hm08 finger landmarks from pinned MakeHuman assets.

Inputs are data only:
- MakeHuman hm08 ``base.obj`` geometry
- MakeHuman bundled ``default.mhskel`` rig asset

No MakeHuman application code is imported or executed. Canonical positions stay
in raw MakeHuman hm08 OBJ coordinates (decimeters); meter conversion is recorded
explicitly for downstream Forge rig construction.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from pathlib import Path

from bootstrap_hm08_head import parse_obj

SCHEMA = "axm.game-assets.hm08-finger-landmarks.v0.1"
FINGER_BONE_RE = re.compile(r"^finger([1-5])-([1-3])\.([LR])$")
RAW_TO_M = 0.1


def _sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _git_blob_sha(path: Path) -> str:
    data = path.read_bytes()
    return hashlib.sha1(f"blob {len(data)}\0".encode("ascii") + data).hexdigest()


def _group_indices(value: object, *, ref: str) -> list[int]:
    if not isinstance(value, list) or not value:
        raise ValueError(f"joint {ref!r} must be a non-empty source-index list")
    result: list[int] = []
    for item in value:
        if isinstance(item, bool) or not isinstance(item, int):
            raise ValueError(f"joint {ref!r} contains non-integer source index {item!r}")
        result.append(int(item))
    return result


def _centroid(vertices: list[tuple[float, float, float]], indices: list[int], *, ref: str) -> tuple[float, float, float]:
    invalid = [index for index in indices if index < 0 or index >= len(vertices)]
    if invalid:
        raise ValueError(f"joint {ref!r} has source indices outside base mesh: {invalid[:8]}")
    count = float(len(indices))
    return tuple(sum(vertices[index][axis] for index in indices) / count for axis in range(3))  # type: ignore[return-value]


def _distance(a: tuple[float, float, float], b: tuple[float, float, float]) -> float:
    return math.sqrt(sum((a[axis] - b[axis]) ** 2 for axis in range(3)))


def derive_finger_landmarks(
    base_obj: str | Path,
    rig_json: str | Path,
    *,
    makehuman_revision: str,
    expected_base_blob_sha1: str | None = None,
    expected_rig_blob_sha1: str | None = None,
    expected_bones: int = 30,
) -> dict[str, object]:
    base_path = Path(base_obj)
    rig_path = Path(rig_json)
    vertices, _uvs, _faces = parse_obj(base_path)
    rig = json.loads(rig_path.read_text(encoding="utf-8"))
    bones = rig.get("bones")
    joints = rig.get("joints")
    if not isinstance(bones, dict) or not isinstance(joints, dict):
        raise ValueError("default.mhskel must contain object-valued bones and joints maps")

    base_blob = _git_blob_sha(base_path)
    rig_blob = _git_blob_sha(rig_path)
    if expected_base_blob_sha1 and base_blob != expected_base_blob_sha1:
        raise ValueError(f"base.obj blob drift: {base_blob} != {expected_base_blob_sha1}")
    if expected_rig_blob_sha1 and rig_blob != expected_rig_blob_sha1:
        raise ValueError(f"default.mhskel blob drift: {rig_blob} != {expected_rig_blob_sha1}")

    rows: list[dict[str, object]] = []
    for bone_name, value in bones.items():
        match = FINGER_BONE_RE.match(str(bone_name))
        if not match:
            continue
        if not isinstance(value, dict):
            raise ValueError(f"finger bone {bone_name!r} must be an object")
        digit, segment, side = int(match.group(1)), int(match.group(2)), match.group(3)
        head_ref = value.get("head")
        tail_ref = value.get("tail")
        if not isinstance(head_ref, str) or not isinstance(tail_ref, str):
            raise ValueError(f"finger bone {bone_name!r} has invalid head/tail references")
        if head_ref not in joints or tail_ref not in joints:
            raise ValueError(f"finger bone {bone_name!r} references missing joints {head_ref!r}/{tail_ref!r}")
        head_indices = _group_indices(joints[head_ref], ref=head_ref)
        tail_indices = _group_indices(joints[tail_ref], ref=tail_ref)
        head_raw = _centroid(vertices, head_indices, ref=head_ref)
        tail_raw = _centroid(vertices, tail_indices, ref=tail_ref)
        length_raw = _distance(head_raw, tail_raw)
        if not math.isfinite(length_raw) or length_raw <= 1e-7:
            raise ValueError(f"finger bone {bone_name!r} has degenerate source length {length_raw}")
        rows.append({
            "source_bone": str(bone_name),
            "side": side,
            "digit": digit,
            "segment": segment,
            "parent_source_bone": value.get("parent"),
            "head_ref": head_ref,
            "tail_ref": tail_ref,
            "head_source_indices": head_indices,
            "tail_source_indices": tail_indices,
            "head_raw": list(head_raw),
            "tail_raw": list(tail_raw),
            "head_m": [component * RAW_TO_M for component in head_raw],
            "tail_m": [component * RAW_TO_M for component in tail_raw],
            "length_raw": length_raw,
            "length_m": length_raw * RAW_TO_M,
        })

    rows.sort(key=lambda row: (str(row["side"]), int(row["digit"]), int(row["segment"])))
    side_counts = {side: sum(1 for row in rows if row["side"] == side) for side in ("L", "R")}
    complete = {
        side: {
            str(digit): sorted(int(row["segment"]) for row in rows if row["side"] == side and row["digit"] == digit)
            for digit in range(1, 6)
        }
        for side in ("L", "R")
    }
    all_source_indices = [index for row in rows for key in ("head_source_indices", "tail_source_indices") for index in row[key]]
    unique_refs = sorted({str(row["head_ref"]) for row in rows} | {str(row["tail_ref"]) for row in rows})
    lengths_m = [float(row["length_m"]) for row in rows]

    acceptance = {
        "exact_finger_bone_count": len(rows) == expected_bones,
        "fifteen_bones_per_hand": side_counts == {"L": 15, "R": 15},
        "five_digits_three_segments_each": all(segments == [1, 2, 3] for side in complete.values() for segments in side.values()),
        "joint_source_groups_nonempty": all(bool(row["head_source_indices"]) and bool(row["tail_source_indices"]) for row in rows),
        "all_source_indices_valid": bool(all_source_indices) and min(all_source_indices) >= 0 and max(all_source_indices) < len(vertices),
        "positive_finite_lengths": bool(lengths_m) and all(math.isfinite(value) and value > 1e-8 for value in lengths_m),
        "raw_coordinate_truth_preserved": RAW_TO_M == 0.1,
    }
    packet: dict[str, object] = {
        "schema": SCHEMA,
        "coordinate_space": {
            "name": "raw_makehuman_hm08_obj",
            "source_unit": "decimeter",
            "downstream_meter_scale": RAW_TO_M,
            "engine_conversion_applied": False,
        },
        "source": {
            "makehuman_revision": makehuman_revision,
            "base_obj_git_blob_sha1": base_blob,
            "base_obj_sha256": _sha256(base_path),
            "default_mhskel_git_blob_sha1": rig_blob,
            "default_mhskel_sha256": _sha256(rig_path),
            "license_record": "MakeHuman bundled base mesh and default.mhskel rig data are used as CC0 source assets under the pinned project LICENSE; no MakeHuman application logic is imported or executed.",
            "license_path": "LICENSE.md",
        },
        "source_vertex_count": len(vertices),
        "finger_bone_count": len(rows),
        "side_counts": side_counts,
        "digit_segments": complete,
        "unique_joint_refs": unique_refs,
        "source_index_range": [min(all_source_indices), max(all_source_indices)] if all_source_indices else None,
        "length_m_range": [min(lengths_m), max(lengths_m)] if lengths_m else None,
        "bones": rows,
        "acceptance": acceptance,
        "truth": {
            "source_grounded": True,
            "application_code_imported": False,
            "production_finger_rig_claim": False,
            "production_finger_skinning_claim": False,
            "notes": [
                "This packet is source landmark data only. Forge still owns the eventual finger skeleton, skin weights, grip solver and engine delivery.",
                "Each landmark is the centroid of the exact source vertex group named by the pinned default.mhskel asset.",
                "Raw hm08 coordinates are retained so the packet can be reconciled against the same canonical full-body source before explicit meter conversion.",
            ],
        },
    }
    if not all(acceptance.values()):
        raise ValueError(f"finger landmark acceptance failed: {acceptance}")
    return packet


def build(args: argparse.Namespace) -> dict[str, object]:
    packet = derive_finger_landmarks(
        args.base_obj,
        args.rig_json,
        makehuman_revision=args.makehuman_revision,
        expected_base_blob_sha1=args.base_blob_sha1,
        expected_rig_blob_sha1=args.rig_blob_sha1,
        expected_bones=args.expected_bones,
    )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    payload = (json.dumps(packet, indent=2, sort_keys=True) + "\n").encode("utf-8")
    output.write_bytes(payload)
    packet["packet_sha256"] = "sha256:" + hashlib.sha256(payload).hexdigest()
    return packet


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser()
    p.add_argument("--base-obj", required=True)
    p.add_argument("--rig-json", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--makehuman-revision", required=True)
    p.add_argument("--base-blob-sha1", default=None)
    p.add_argument("--rig-blob-sha1", default=None)
    p.add_argument("--expected-bones", type=int, default=30)
    return p


if __name__ == "__main__":
    result = build(parser().parse_args())
    print(json.dumps({
        "acceptance": result["acceptance"],
        "finger_bone_count": result["finger_bone_count"],
        "source_index_range": result["source_index_range"],
        "length_m_range": result["length_m_range"],
    }, indent=2))
