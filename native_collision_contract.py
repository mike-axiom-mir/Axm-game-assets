#!/usr/bin/env python3
"""Explicit coarse collision/navigation contracts for AXM Game Asset Forge.

Selectively adapted from Universal Creation's finished RTS foundry
``src/axm_uc/rts_foundry.py::collision_contract`` at commit
``a5cc708457b7e8f33e794fdac648ae65d15a0fb4``.

The useful donor idea is semantic collision state, not automatic physics:
multiple named box proxies, role labels, explicit conditional behavior and XZ
navigation footprints are kept as authored evidence. No engine behavior is
silently inferred from the visual mesh.
"""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

from native_geometry import Mesh, bounds, combine, make_box, topology_report, translate, write_obj

SCHEMA = "axm.game-assets.collision-contract/v0.1"
DONOR = {
    "repo": "mike-axiom-mir/axm-universal-creation",
    "commit": "a5cc708457b7e8f33e794fdac648ae65d15a0fb4",
    "mechanism": "src/axm_uc/rts_foundry.py::collision_contract",
}


class CollisionContractError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class CollisionBox:
    proxy_id: str
    center: tuple[float, float, float]
    size: tuple[float, float, float]
    role: str = "solid"
    condition: str | None = None


@dataclass(frozen=True, slots=True)
class CollisionContract:
    asset_id: str
    boxes: tuple[CollisionBox, ...]
    equipment_blocks_navigation: bool = True
    basis: str = "Explicit authored coarse gameplay proxies; no automatic physics-engine fit"


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")


def _digest(value: Any) -> str:
    return "sha256:" + hashlib.sha256(_canonical(value)).hexdigest()


def _finite3(value: Sequence[float], label: str) -> tuple[float, float, float]:
    if len(value) != 3:
        raise CollisionContractError(f"{label} must contain three values")
    result = tuple(float(item) for item in value)
    if not all(math.isfinite(item) for item in result):
        raise CollisionContractError(f"{label} must contain finite values")
    return result  # type: ignore[return-value]


def _box_payload(box: CollisionBox) -> dict[str, Any]:
    center = _finite3(box.center, f"proxy {box.proxy_id} center")
    size = _finite3(box.size, f"proxy {box.proxy_id} size")
    if any(value <= 0.0 for value in size):
        raise CollisionContractError(f"proxy {box.proxy_id!r} sizes must be positive")
    if not box.proxy_id.strip():
        raise CollisionContractError("collision proxy id must be non-empty")
    if not box.role.strip():
        raise CollisionContractError(f"proxy {box.proxy_id!r} role must be non-empty")
    if box.condition is not None and not box.condition.strip():
        raise CollisionContractError(f"proxy {box.proxy_id!r} condition must be non-empty when supplied")
    cx, cy, cz = center
    sx, sy, sz = size
    footprint = [
        [cx - sx * .5, cz - sz * .5],
        [cx + sx * .5, cz - sz * .5],
        [cx + sx * .5, cz + sz * .5],
        [cx - sx * .5, cz + sz * .5],
    ]
    payload: dict[str, Any] = {
        "proxy_id": box.proxy_id,
        "shape": "box",
        "center": list(center),
        "size": list(size),
        "role": box.role,
        "navigation_polygon_xz": footprint,
    }
    if box.condition is not None:
        payload["condition"] = box.condition
    return payload


def contract_payload(contract: CollisionContract) -> dict[str, Any]:
    if not isinstance(contract.asset_id, str) or not contract.asset_id.strip():
        raise CollisionContractError("asset_id must be non-empty")
    if not contract.boxes:
        raise CollisionContractError("collision contract needs at least one explicit proxy")
    seen: set[str] = set()
    boxes = []
    for box in contract.boxes:
        if box.proxy_id in seen:
            raise CollisionContractError(f"duplicate collision proxy id {box.proxy_id!r}")
        seen.add(box.proxy_id)
        boxes.append(_box_payload(box))
    return {
        "schema": SCHEMA,
        "asset_id": contract.asset_id,
        "basis": contract.basis,
        "boxes": boxes,
        "navigation_polygons_xz": [box["navigation_polygon_xz"] for box in boxes],
        "conditional_roles": {
            box["proxy_id"]: box["condition"]
            for box in boxes
            if "condition" in box
        },
        "equipment_blocks_navigation": bool(contract.equipment_blocks_navigation),
        "provenance": {"donor": DONOR, "implementation": "AXM Game Asset Forge native semantic collision port"},
        "truth_boundary": {
            "authored_proxy_geometry": True,
            "navigation_footprints_derived_from_proxy_boxes": True,
            "automatic_visual_mesh_fit": False,
            "physics_engine_tested": False,
            "pathfinding_tested": False,
            "automatic_genome_mutation": False,
            "automatic_canon": False,
        },
    }


def validate_collision_contract(contract: CollisionContract) -> dict[str, Any]:
    try:
        payload = contract_payload(contract)
    except CollisionContractError as exc:
        return {"status": "fail", "failures": [str(exc)]}
    return {
        "status": "pass",
        "failures": [],
        "asset_id": payload["asset_id"],
        "box_count": len(payload["boxes"]),
        "conditional_count": len(payload["conditional_roles"]),
        "contract_digest": _digest(payload),
    }


def collision_proxy_mesh(contract: CollisionContract, *, name: str | None = None) -> Mesh:
    payload = contract_payload(contract)
    parts = []
    for box in payload["boxes"]:
        mesh = make_box(tuple(box["size"]), name=f"collision:{box['proxy_id']}")
        parts.append(translate(mesh, tuple(box["center"]), name=mesh.name))
    combined = combine(parts, name=name or f"{contract.asset_id}-collision")
    report = topology_report(combined)
    if report["invalid_indices"] or report["degenerate_faces"]:
        raise CollisionContractError(f"generated collision proxy mesh is structurally invalid: {report}")
    return combined


def coarse_contract_from_mesh(
    mesh: Mesh,
    *,
    asset_id: str,
    scale: Sequence[float] = (.80, 1.0, .72),
    role: str = "coarse-placement-proxy",
    equipment_blocks_navigation: bool = True,
) -> CollisionContract:
    """Create one explicitly labelled coarse AABB-derived proxy.

    This helper is intentionally not called an automatic collider fit. The
    caller supplies the shrink/expansion scale and the resulting role remains
    coarse-placement evidence until a gameplay/physics consumer accepts it.
    """
    factors = _finite3(scale, "coarse proxy scale")
    if any(value <= 0.0 for value in factors):
        raise CollisionContractError("coarse proxy scale values must be positive")
    lo, hi = bounds(mesh)
    span = tuple(hi[i] - lo[i] for i in range(3))
    if any(value <= 0.0 for value in span):
        raise CollisionContractError("source mesh bounds must have positive span on all axes")
    center = tuple((lo[i] + hi[i]) * .5 for i in range(3))
    size = tuple(span[i] * factors[i] for i in range(3))
    return CollisionContract(
        asset_id,
        (CollisionBox("coarse-main", center, size, role),),
        equipment_blocks_navigation=equipment_blocks_navigation,
        basis=(
            "Caller-parameterized AABB-derived coarse proxy; scale="
            + ",".join(f"{value:.6g}" for value in factors)
            + ". Not an automatic production collider fit."
        ),
    )


def write_collision_contract(contract: CollisionContract, output: str | Path) -> dict[str, Any]:
    root = Path(output)
    root.mkdir(parents=True, exist_ok=True)
    json_path = root / "collision-contract.json"
    obj_path = root / "collision-proxy.obj"
    receipt_path = root / "collision-receipt.json"
    if any(path.exists() for path in (json_path, obj_path, receipt_path)):
        raise FileExistsError("collision delivery refuses to overwrite existing output")
    payload = contract_payload(contract)
    payload["contract_digest"] = _digest(payload)
    json_bytes = (json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")
    json_path.write_bytes(json_bytes)
    mesh = collision_proxy_mesh(contract)
    write_obj(mesh, obj_path)
    obj_bytes = obj_path.read_bytes()
    receipt: dict[str, Any] = {
        "schema": SCHEMA,
        "status": "PASS",
        "asset_id": contract.asset_id,
        "contract": {"path": json_path.name, "sha256": "sha256:" + hashlib.sha256(json_bytes).hexdigest(), "bytes": len(json_bytes)},
        "proxy_mesh": {"path": obj_path.name, "sha256": "sha256:" + hashlib.sha256(obj_bytes).hexdigest(), "bytes": len(obj_bytes), "topology": topology_report(mesh)},
        "authority": {
            "automatic_install": False,
            "automatic_genome_mutation": False,
            "physics_acceptance": False,
            "navigation_acceptance": False,
            "release": False,
            "merge": False,
            "canon": False,
        },
        "truth_boundary": {
            "proves": ["declared coarse proxy box geometry", "derived XZ footprints", "exact written contract/proxy identities"],
            "does_not_prove": ["physics behavior", "pathfinding behavior", "visual mesh fidelity", "gameplay suitability", "target-engine acceptance"],
        },
        "provenance": DONOR,
    }
    receipt["receipt_digest"] = _digest(receipt)
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return receipt
