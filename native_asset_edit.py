#!/usr/bin/env python3
"""AXM deterministic asset edit surface and packet engine v0.1.

The editor never owns canonical asset truth. A surface declares which semantic
parameters a player/AI/tool may edit and maps those parameters onto bounded
variant-state paths. An edit packet can only address declared parameter IDs.
Applying a packet creates a deterministic derived variant + receipt and never
mutates the supplied base state.
"""
from __future__ import annotations

import copy
import hashlib
import json
from typing import Any

SURFACE_SCHEMA = "axm.asset-edit-surface.v0.1"
PACKET_SCHEMA = "axm.asset-edit-packet.v0.1"
RESULT_SCHEMA = "axm.asset-edit-result.v0.1"
ACTOR_KINDS = {"player", "ai", "tool"}
PARAM_TYPES = {"number", "integer", "boolean", "enum", "string"}


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def digest(value: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_bytes(value)).hexdigest()


def _set_path(root: dict[str, Any], dotted_path: str, value: Any) -> None:
    parts = [part for part in dotted_path.split(".") if part]
    if not parts:
        raise ValueError("edit path must not be empty")
    cursor = root
    for part in parts[:-1]:
        existing = cursor.get(part)
        if existing is None:
            existing = {}
            cursor[part] = existing
        if not isinstance(existing, dict):
            raise ValueError(f"edit path crosses non-object at {part!r}")
        cursor = existing
    cursor[parts[-1]] = copy.deepcopy(value)


def _validate_value(parameter: dict[str, Any], value: Any) -> list[str]:
    failures: list[str] = []
    kind = parameter.get("type")
    pid = parameter.get("id", "<unknown>")
    if kind == "number":
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            failures.append(f"{pid}: value must be numeric")
        else:
            numeric = float(value)
            if "minimum" in parameter and numeric < float(parameter["minimum"]):
                failures.append(f"{pid}: value below minimum")
            if "maximum" in parameter and numeric > float(parameter["maximum"]):
                failures.append(f"{pid}: value above maximum")
    elif kind == "integer":
        if isinstance(value, bool) or not isinstance(value, int):
            failures.append(f"{pid}: value must be integer")
        else:
            if "minimum" in parameter and value < int(parameter["minimum"]):
                failures.append(f"{pid}: value below minimum")
            if "maximum" in parameter and value > int(parameter["maximum"]):
                failures.append(f"{pid}: value above maximum")
    elif kind == "boolean":
        if not isinstance(value, bool):
            failures.append(f"{pid}: value must be boolean")
    elif kind == "enum":
        values = parameter.get("values", [])
        if value not in values:
            failures.append(f"{pid}: value is not an allowed enum member")
    elif kind == "string":
        if not isinstance(value, str):
            failures.append(f"{pid}: value must be string")
        else:
            max_length = int(parameter.get("max_length", 256))
            if len(value) > max_length:
                failures.append(f"{pid}: string exceeds max_length")
    else:
        failures.append(f"{pid}: unsupported parameter type {kind!r}")
    return failures


def validate_surface(surface: dict[str, Any]) -> dict[str, Any]:
    failures: list[str] = []
    if surface.get("schema") != SURFACE_SCHEMA:
        failures.append("unsupported edit-surface schema")
    if not str(surface.get("surface_id", "")).strip():
        failures.append("surface_id is required")
    if not str(surface.get("asset_family", "")).strip():
        failures.append("asset_family is required")
    parameters = surface.get("parameters")
    if not isinstance(parameters, list) or not parameters:
        failures.append("parameters must be a non-empty list")
        parameters = []
    seen_ids: set[str] = set()
    seen_paths: set[str] = set()
    for index, parameter in enumerate(parameters):
        if not isinstance(parameter, dict):
            failures.append(f"parameter {index} must be an object")
            continue
        pid = str(parameter.get("id", "")).strip()
        path = str(parameter.get("path", "")).strip()
        if not pid:
            failures.append(f"parameter {index} id is required")
        elif pid in seen_ids:
            failures.append(f"duplicate parameter id {pid}")
        seen_ids.add(pid)
        if not path:
            failures.append(f"parameter {pid or index} path is required")
        elif path in seen_paths:
            failures.append(f"duplicate parameter path {path}")
        seen_paths.add(path)
        kind = parameter.get("type")
        if kind not in PARAM_TYPES:
            failures.append(f"parameter {pid or index} has unsupported type {kind!r}")
        editable_by = parameter.get("editable_by", [])
        if not isinstance(editable_by, list) or not editable_by:
            failures.append(f"parameter {pid or index} editable_by must be non-empty")
        elif any(actor not in ACTOR_KINDS for actor in editable_by):
            failures.append(f"parameter {pid or index} has invalid editable_by actor")
        if kind == "enum":
            values = parameter.get("values")
            if not isinstance(values, list) or not values or len(values) != len(set(map(str, values))):
                failures.append(f"parameter {pid or index} enum values must be unique and non-empty")
        if kind in {"number", "integer"} and "minimum" in parameter and "maximum" in parameter:
            if float(parameter["minimum"]) > float(parameter["maximum"]):
                failures.append(f"parameter {pid or index} minimum exceeds maximum")
        if "default" in parameter:
            failures.extend(_validate_value(parameter, parameter["default"]))
    return {
        "status": "pass" if not failures else "fail",
        "failures": failures,
        "parameters": len(parameters),
        "surface_digest": digest(surface),
    }


def validate_packet(packet: dict[str, Any], surface: dict[str, Any]) -> dict[str, Any]:
    failures: list[str] = []
    surface_report = validate_surface(surface)
    if surface_report["status"] != "pass":
        failures.append("edit surface is invalid")
    if packet.get("schema") != PACKET_SCHEMA:
        failures.append("unsupported edit-packet schema")
    if packet.get("surface_id") != surface.get("surface_id"):
        failures.append("packet surface_id does not match edit surface")
    base_digest = str(packet.get("base_genome_digest", ""))
    if not base_digest.startswith("sha256:") or len(base_digest) != 71:
        failures.append("base_genome_digest must be sha256:<64 hex>")
    actor = packet.get("actor", {})
    actor_kind = actor.get("kind") if isinstance(actor, dict) else None
    if actor_kind not in ACTOR_KINDS:
        failures.append("actor.kind must be player, ai, or tool")
    operations = packet.get("operations")
    if not isinstance(operations, list):
        failures.append("operations must be a list")
        operations = []
    lookup = {
        parameter["id"]: parameter
        for parameter in surface.get("parameters", [])
        if isinstance(parameter, dict) and "id" in parameter
    }
    seen: set[str] = set()
    for index, operation in enumerate(operations):
        if not isinstance(operation, dict):
            failures.append(f"operation {index} must be an object")
            continue
        if operation.get("op", "set") != "set":
            failures.append(f"operation {index}: only deterministic set is supported in v0.1")
            continue
        pid = operation.get("parameter")
        if pid in seen:
            failures.append(f"operation {index}: duplicate parameter {pid}")
        seen.add(pid)
        parameter = lookup.get(pid)
        if parameter is None:
            failures.append(f"operation {index}: undeclared parameter {pid!r}")
            continue
        if actor_kind not in parameter.get("editable_by", []):
            failures.append(f"operation {index}: actor {actor_kind!r} may not edit {pid!r}")
        failures.extend(_validate_value(parameter, operation.get("value")))
    return {
        "status": "pass" if not failures else "fail",
        "failures": failures,
        "operations": len(operations),
        "packet_digest": digest(packet),
        "surface_digest": surface_report["surface_digest"],
    }


def apply_edit_packet(
    base_variant_state: dict[str, Any],
    surface: dict[str, Any],
    packet: dict[str, Any],
) -> dict[str, Any]:
    report = validate_packet(packet, surface)
    if report["status"] != "pass":
        raise ValueError(f"invalid asset edit packet: {report}")
    variant_state = copy.deepcopy(base_variant_state)
    lookup = {parameter["id"]: parameter for parameter in surface["parameters"]}
    applied: list[dict[str, Any]] = []
    for operation in packet["operations"]:
        parameter = lookup[operation["parameter"]]
        value = copy.deepcopy(operation["value"])
        _set_path(variant_state, parameter["path"], value)
        applied.append({
            "parameter": parameter["id"],
            "path": parameter["path"],
            "value": value,
        })
    variant_payload = {
        "base_genome_digest": packet["base_genome_digest"],
        "surface_digest": report["surface_digest"],
        "variant_state": variant_state,
    }
    result = {
        "schema": RESULT_SCHEMA,
        "surface_id": surface["surface_id"],
        "asset_family": surface["asset_family"],
        "base_genome_digest": packet["base_genome_digest"],
        "surface_digest": report["surface_digest"],
        "edit_packet_digest": report["packet_digest"],
        "actor": copy.deepcopy(packet["actor"]),
        "applied": applied,
        "variant_state": variant_state,
        "variant_digest": digest(variant_payload),
        "truth": {
            "canonical_state_mutated": False,
            "authority": "derived_variant_state_only",
            "notes": [
                "The edit packet cannot address paths that are absent from the declared surface.",
                "A game/editor may expose a subset of Forge capability without owning canonical asset truth."
            ],
        },
    }
    result["result_digest"] = digest(result)
    return result
