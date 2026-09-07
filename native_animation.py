#!/usr/bin/env python3
"""AXM native skeletal animation state, sampling, and contact-drift evidence v0.1."""
from __future__ import annotations

from dataclasses import dataclass, replace
from math import isfinite, sqrt
from typing import Sequence

from native_geometry import Mesh
from native_skin import Quat, Skeleton, SkinWeights, normalize_quaternion, skin_vertices, validate_skeleton

AnimValue = tuple[float, ...]


@dataclass(slots=True)
class AnimationTrack:
    joint: int
    path: str
    times: list[float]
    values: list[AnimValue]
    interpolation: str = "LINEAR"


@dataclass(slots=True)
class AnimationClip:
    name: str
    tracks: list[AnimationTrack]


def _finite(values: Sequence[float]) -> bool:
    return all(isfinite(float(value)) for value in values)


def validate_animation_clip(clip: AnimationClip, skeleton: Skeleton) -> dict[str, object]:
    failures: list[str] = []
    skeleton_report = validate_skeleton(skeleton)
    if skeleton_report["status"] != "pass":
        failures.append("skeleton invalid")
    if not clip.name.strip():
        failures.append("animation name must be non-empty")
    seen_targets: set[tuple[int, str]] = set()
    allowed = {"translation": 3, "rotation": 4, "scale": 3}
    for index, track in enumerate(clip.tracks):
        if track.joint < 0 or track.joint >= len(skeleton.joints):
            failures.append(f"track {index} joint outside skeleton")
        if track.path not in allowed:
            failures.append(f"track {index} unsupported path {track.path}")
            continue
        target = (track.joint, track.path)
        if target in seen_targets:
            failures.append(f"duplicate track target joint={track.joint} path={track.path}")
        seen_targets.add(target)
        if track.interpolation not in {"LINEAR", "STEP"}:
            failures.append(f"track {index} unsupported interpolation {track.interpolation}")
        if len(track.times) != len(track.values) or not track.times:
            failures.append(f"track {index} needs equal non-empty times/values")
            continue
        if not _finite(track.times):
            failures.append(f"track {index} contains non-finite time")
        if any(b <= a for a, b in zip(track.times, track.times[1:])):
            failures.append(f"track {index} times must increase strictly")
        if track.times[0] < 0.0:
            failures.append(f"track {index} starts before t=0")
        width = allowed[track.path]
        for key, value in enumerate(track.values):
            if len(value) != width or not _finite(value):
                failures.append(f"track {index} key {key} has invalid {track.path} value")
                continue
            if track.path == "rotation":
                length = sqrt(sum(component * component for component in value))
                if abs(length - 1.0) > 1e-5:
                    failures.append(f"track {index} key {key} quaternion must be normalized")
            if track.path == "scale" and any(abs(component) <= 1e-12 for component in value):
                failures.append(f"track {index} key {key} scale must be non-zero")
    duration = max((track.times[-1] for track in clip.tracks if track.times), default=0.0)
    return {"status": "pass" if not failures else "fail", "failures": failures, "tracks": len(clip.tracks), "duration": duration}


def _lerp(a: Sequence[float], b: Sequence[float], t: float) -> tuple[float, ...]:
    return tuple(x + (y - x) * t for x, y in zip(a, b))


def _nlerp_quat(a: Quat, b: Quat, t: float) -> Quat:
    dot = sum(x * y for x, y in zip(a, b))
    if dot < 0.0:
        b = tuple(-value for value in b)  # type: ignore[assignment]
    return normalize_quaternion(_lerp(a, b, t))  # type: ignore[arg-type]


def sample_track(track: AnimationTrack, time: float) -> AnimValue:
    if not track.times:
        raise ValueError("cannot sample empty track")
    if time <= track.times[0]:
        return track.values[0]
    if time >= track.times[-1]:
        return track.values[-1]
    for index, (a_time, b_time) in enumerate(zip(track.times, track.times[1:])):
        if a_time <= time <= b_time:
            if track.interpolation == "STEP":
                return track.values[index]
            t = (time - a_time) / (b_time - a_time)
            if track.path == "rotation":
                return _nlerp_quat(track.values[index], track.values[index + 1], t)  # type: ignore[arg-type]
            return _lerp(track.values[index], track.values[index + 1], t)
    return track.values[-1]


def pose_skeleton(bind_skeleton: Skeleton, clip: AnimationClip, time: float) -> Skeleton:
    report = validate_animation_clip(clip, bind_skeleton)
    if report["status"] != "pass":
        raise ValueError(f"invalid animation clip: {report}")
    joints = list(bind_skeleton.joints)
    for track in clip.tracks:
        value = sample_track(track, time)
        joint = joints[track.joint]
        if track.path == "translation":
            joints[track.joint] = replace(joint, translation=tuple(value))  # type: ignore[arg-type]
        elif track.path == "rotation":
            joints[track.joint] = replace(joint, rotation=tuple(value))  # type: ignore[arg-type]
        elif track.path == "scale":
            joints[track.joint] = replace(joint, scale=tuple(value))  # type: ignore[arg-type]
    return Skeleton(joints)


def contact_drift(
    mesh: Mesh,
    skin_weights: SkinWeights,
    bind_skeleton: Skeleton,
    clip: AnimationClip,
    vertex_indices: Sequence[int],
    sample_times: Sequence[float],
) -> dict[str, object]:
    if not vertex_indices:
        raise ValueError("contact drift needs at least one vertex")
    if not sample_times:
        raise ValueError("contact drift needs sample times")
    if any(index < 0 or index >= len(mesh.vertices) for index in vertex_indices):
        raise ValueError("contact vertex outside mesh")
    poses = []
    for time in sample_times:
        posed = pose_skeleton(bind_skeleton, clip, time)
        vertices = skin_vertices(mesh, skin_weights, bind_skeleton, posed)
        centroid = tuple(sum(vertices[index][axis] for index in vertex_indices) / len(vertex_indices) for axis in range(3))
        poses.append((float(time), centroid))
    origin = poses[0][1]
    distances = []
    for time, point in poses:
        distance = sqrt(sum((point[axis] - origin[axis]) ** 2 for axis in range(3)))
        distances.append((time, distance))
    max_time, maximum = max(distances, key=lambda item: item[1])
    return {
        "samples": len(sample_times),
        "vertices": list(vertex_indices),
        "max_drift": maximum,
        "max_drift_time": max_time,
        "trajectory": [{"time": time, "distance_from_start": distance} for time, distance in distances],
    }
