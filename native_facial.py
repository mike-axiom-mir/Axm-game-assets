#!/usr/bin/env python3
"""AXM native facial/corrective driver and morph-weight animation state v0.1."""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Mapping, Sequence


@dataclass(frozen=True, slots=True)
class DriverCondition:
    signal: str
    start: float
    end: float


@dataclass(frozen=True, slots=True)
class CorrectiveRule:
    name: str
    target: str
    conditions: tuple[DriverCondition, ...]
    gain: float = 1.0
    combine: str = "product"


@dataclass(slots=True)
class MorphWeightClip:
    name: str
    times: list[float]
    values: list[tuple[float, ...]]
    interpolation: str = "LINEAR"


def condition_weight(value: float, condition: DriverCondition) -> float:
    if not isfinite(value) or not isfinite(condition.start) or not isfinite(condition.end):
        raise ValueError("corrective driver values must be finite")
    if condition.start == condition.end:
        return 1.0 if value >= condition.end else 0.0
    t = (value - condition.start) / (condition.end - condition.start)
    return max(0.0, min(1.0, t))


def evaluate_correctives(
    signals: Mapping[str, float],
    target_names: Sequence[str],
    rules: Sequence[CorrectiveRule],
    *,
    base_weights: Mapping[str, float] | None = None,
) -> dict[str, object]:
    target_set = set(target_names)
    if len(target_set) != len(target_names):
        raise ValueError("target_names must be unique")
    weights = {name: 0.0 for name in target_names}
    for name, value in (base_weights or {}).items():
        if name not in target_set:
            raise ValueError(f"unknown base morph target {name!r}")
        if not isfinite(float(value)):
            raise ValueError(f"base morph target {name!r} has non-finite weight")
        weights[name] = max(0.0, min(1.0, float(value)))

    evidence = []
    for rule in rules:
        if not rule.name.strip() or not rule.target.strip():
            raise ValueError("corrective rule name/target must be non-empty")
        if rule.target not in target_set:
            raise ValueError(f"corrective {rule.name!r} targets unknown morph {rule.target!r}")
        if not rule.conditions:
            raise ValueError(f"corrective {rule.name!r} needs at least one condition")
        if rule.combine not in {"product", "min", "max"}:
            raise ValueError(f"unsupported corrective combine mode {rule.combine!r}")
        if not isfinite(rule.gain) or rule.gain < 0.0:
            raise ValueError(f"corrective {rule.name!r} gain must be finite and non-negative")
        values = []
        for condition in rule.conditions:
            if condition.signal not in signals:
                raise ValueError(f"corrective {rule.name!r} missing driver signal {condition.signal!r}")
            values.append(condition_weight(float(signals[condition.signal]), condition))
        if rule.combine == "product":
            activation = 1.0
            for value in values:
                activation *= value
        elif rule.combine == "min":
            activation = min(values)
        else:
            activation = max(values)
        contribution = max(0.0, min(1.0, activation * rule.gain))
        weights[rule.target] = max(0.0, min(1.0, weights[rule.target] + contribution))
        evidence.append({
            "rule": rule.name,
            "target": rule.target,
            "driver_weights": values,
            "activation": activation,
            "gain": rule.gain,
            "contribution": contribution,
        })
    return {"weights": weights, "rules": evidence}


def validate_morph_weight_clip(clip: MorphWeightClip, morph_count: int) -> dict[str, object]:
    failures = []
    if not clip.name.strip():
        failures.append("morph-weight clip name must be non-empty")
    if morph_count <= 0:
        failures.append("morph-weight animation needs at least one target")
    if clip.interpolation not in {"LINEAR", "STEP"}:
        failures.append(f"unsupported interpolation {clip.interpolation}")
    if len(clip.times) != len(clip.values) or not clip.times:
        failures.append("clip needs equal non-empty times and values")
    if any(not isfinite(float(time)) or time < 0.0 for time in clip.times):
        failures.append("clip times must be finite and non-negative")
    if any(b <= a for a, b in zip(clip.times, clip.times[1:])):
        failures.append("clip times must increase strictly")
    for index, row in enumerate(clip.values):
        if len(row) != morph_count:
            failures.append(f"key {index} has {len(row)} weights, expected {morph_count}")
            continue
        if any(not isfinite(float(value)) for value in row):
            failures.append(f"key {index} contains non-finite morph weight")
        if any(value < 0.0 or value > 1.0 for value in row):
            failures.append(f"key {index} morph weights must stay in [0,1]")
    return {
        "status": "pass" if not failures else "fail",
        "failures": failures,
        "name": clip.name,
        "keys": len(clip.times),
        "morph_count": morph_count,
        "duration": clip.times[-1] if clip.times else 0.0,
    }


def sample_morph_weight_clip(clip: MorphWeightClip, time: float) -> tuple[float, ...]:
    report = validate_morph_weight_clip(clip, len(clip.values[0]) if clip.values else 0)
    if report["status"] != "pass":
        raise ValueError(f"invalid morph-weight clip: {report}")
    if time <= clip.times[0]:
        return clip.values[0]
    if time >= clip.times[-1]:
        return clip.values[-1]
    for index, (a_time, b_time) in enumerate(zip(clip.times, clip.times[1:])):
        if a_time <= time <= b_time:
            if clip.interpolation == "STEP":
                return clip.values[index]
            t = (time - a_time) / (b_time - a_time)
            return tuple(a + (b - a) * t for a, b in zip(clip.values[index], clip.values[index + 1]))
    return clip.values[-1]
