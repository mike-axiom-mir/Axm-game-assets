#!/usr/bin/env python3
"""AXM visual capture and observation evidence contracts v0.1.

Capture facts and quality judgments are deliberately separate. A deterministic
screenshot receipt can prove what bytes were rendered under which engine state;
it cannot silently elevate an aesthetic observation into canonical truth.
"""
from __future__ import annotations

import hashlib
import json
import struct
from dataclasses import dataclass
from math import isfinite
from pathlib import Path
from typing import Any, Mapping, Sequence

CAPTURE_SCHEMA = "axm.game-assets.visual-capture.v0.1"
OBSERVATION_SCHEMA = "axm.game-assets.visual-observation.v0.1"


def _sha(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def png_dimensions(data: bytes) -> tuple[int, int]:
    if len(data) < 24 or data[:8] != b"\x89PNG\r\n\x1a\n" or data[12:16] != b"IHDR":
        raise ValueError("capture is not a valid PNG header")
    width, height = struct.unpack(">II", data[16:24])
    if width <= 0 or height <= 0:
        raise ValueError("PNG dimensions must be positive")
    return width, height


def build_capture_packet(
    png: bytes,
    *,
    asset_digest: str,
    engine: Mapping[str, Any],
    camera: Mapping[str, Any],
    render_settings: Mapping[str, Any],
    metrics: Mapping[str, Any] | None = None,
    source_receipts: Sequence[str] = (),
) -> dict[str, Any]:
    if not asset_digest.startswith("sha256:"):
        raise ValueError("asset_digest must be a sha256 receipt")
    width, height = png_dimensions(png)
    packet: dict[str, Any] = {
        "schema": CAPTURE_SCHEMA,
        "authority": "deterministic_capture_fact",
        "image": {
            "mime": "image/png",
            "sha256": _sha(png),
            "bytes": len(png),
            "width": width,
            "height": height,
        },
        "asset_digest": asset_digest,
        "engine": dict(engine),
        "camera": dict(camera),
        "render_settings": dict(render_settings),
        "metrics": dict(metrics or {}),
        "source_receipts": list(source_receipts),
        "truth": {
            "what_it_can_prove": [
                "the exact screenshot bytes",
                "the declared engine/camera/render context tied to this packet",
                "deterministic numeric metrics copied into this receipt",
            ],
            "what_it_cannot_prove": [
                "that the asset is beautiful",
                "that the asset is AAA quality",
                "that an observer's preference is objective truth",
            ],
        },
    }
    packet["capture_digest"] = _sha(_canonical(packet))
    return packet


def validate_capture_packet(packet: Mapping[str, Any], png: bytes) -> dict[str, Any]:
    failures: list[str] = []
    if packet.get("schema") != CAPTURE_SCHEMA:
        failures.append("unsupported capture schema")
    if packet.get("authority") != "deterministic_capture_fact":
        failures.append("capture authority must remain deterministic_capture_fact")
    image = packet.get("image")
    if not isinstance(image, Mapping):
        failures.append("capture image record missing")
    else:
        try:
            width, height = png_dimensions(png)
        except ValueError as exc:
            failures.append(str(exc))
        else:
            if image.get("sha256") != _sha(png):
                failures.append("PNG digest differs from capture receipt")
            if image.get("bytes") != len(png):
                failures.append("PNG byte count differs from capture receipt")
            if image.get("width") != width or image.get("height") != height:
                failures.append("PNG dimensions differ from capture receipt")
    return {"status": "pass" if not failures else "fail", "failures": failures}


@dataclass(frozen=True, slots=True)
class CriterionObservation:
    criterion: str
    score: float | None
    confidence: float
    note: str
    evidence_refs: tuple[str, ...] = ()


def build_observation_packet(
    capture_digest: str,
    observations: Sequence[CriterionObservation],
    *,
    observer: Mapping[str, Any],
    rubric_id: str,
) -> dict[str, Any]:
    if not capture_digest.startswith("sha256:"):
        raise ValueError("observation must reference a capture digest")
    if not rubric_id.strip():
        raise ValueError("rubric_id is required")
    if not observations:
        raise ValueError("observation packet needs at least one criterion")
    rows = []
    for item in observations:
        if not item.criterion.strip():
            raise ValueError("criterion name must be non-empty")
        if item.score is not None and (not isfinite(item.score) or item.score < 0.0 or item.score > 1.0):
            raise ValueError(f"criterion {item.criterion!r} score must be within [0,1]")
        if not isfinite(item.confidence) or item.confidence < 0.0 or item.confidence > 1.0:
            raise ValueError(f"criterion {item.criterion!r} confidence must be within [0,1]")
        rows.append({
            "criterion": item.criterion,
            "score": item.score,
            "confidence": item.confidence,
            "note": item.note,
            "evidence_refs": list(item.evidence_refs),
        })
    packet: dict[str, Any] = {
        "schema": OBSERVATION_SCHEMA,
        "authority": "advisory_observation",
        "capture_digest": capture_digest,
        "rubric_id": rubric_id,
        "observer": dict(observer),
        "observations": rows,
        "truth": {
            "automatic_canon": False,
            "notes": [
                "Scores are observations under a named rubric, not automatic truth claims.",
                "A later explicit merge/acceptance gate may use these observations alongside technical evidence.",
                "Missing or low-confidence observations remain visible rather than being silently filled in.",
            ],
        },
    }
    packet["observation_digest"] = _sha(_canonical(packet))
    return packet


def summarize_observation(packet: Mapping[str, Any]) -> dict[str, Any]:
    if packet.get("schema") != OBSERVATION_SCHEMA:
        raise ValueError("unsupported observation schema")
    rows = packet.get("observations")
    if not isinstance(rows, list) or not rows:
        raise ValueError("observation rows missing")
    weighted_score = 0.0
    total_confidence = 0.0
    scored = 0
    unscored = 0
    for row in rows:
        score = row.get("score")
        confidence = float(row.get("confidence", 0.0))
        if score is None:
            unscored += 1
            continue
        weighted_score += float(score) * confidence
        total_confidence += confidence
        scored += 1
    return {
        "scored_criteria": scored,
        "unscored_criteria": unscored,
        "confidence_weighted_score": weighted_score / total_confidence if total_confidence > 0.0 else None,
        "authority": "advisory_summary",
        "automatic_canon": False,
    }


def write_capture_packet(path: str | Path, packet: Mapping[str, Any]) -> None:
    Path(path).write_text(json.dumps(packet, indent=2, sort_keys=True) + "\n", encoding="utf-8")
