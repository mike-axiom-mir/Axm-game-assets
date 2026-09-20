#!/usr/bin/env python3
"""Explicit reusable-part library for AXM Game Asset Forge.

A finished asset is already persistent in its own Game Asset Genome/source state.
This module does NOT auto-promote every successful part into a global library.

Instead:
    source assembly -> scan -> user/AI selects useful parts -> pull -> verify

Geometry is content-addressed independently from material/style labels, so the same
shape painted ten colours remains one geometry atom. Semantic/library items may
refer to that atom with different roles/material families without duplicating the
mesh bytes.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Iterable

from native_construction_kit import ConstructionAssembly, SemanticPart
from native_geometry import Mesh, topology_report

SCHEMA = "axm.game-assets.reusable-part-library/v0.1"
OBJECT_SCHEMA = "axm.game-assets.geometry-atom/v0.1"
INDEX_NAME = "library.json"


class ReusablePartLibraryError(ValueError):
    pass


def _canonical(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ReusablePartLibraryError("part-library values must be finite JSON data") from exc


def _digest(value: Any) -> str:
    return "sha256:" + hashlib.sha256(_canonical(value)).hexdigest()


def _geometry_payload(mesh: Mesh) -> dict[str, Any]:
    report = topology_report(mesh)
    if report["invalid_indices"] or report["degenerate_faces"]:
        raise ReusablePartLibraryError(
            f"cannot library invalid geometry {mesh.name!r}: {report}"
        )
    return {
        "schema": OBJECT_SCHEMA,
        "vertices": [list(row) for row in mesh.vertices],
        "faces": [list(face) for face in mesh.faces],
        "topology": report,
    }


def geometry_digest(mesh: Mesh) -> str:
    return _digest(_geometry_payload(mesh))


def semantic_item_digest(part: SemanticPart) -> str:
    return _digest({
        "geometry": geometry_digest(part.mesh),
        "material_family": part.material_family,
        "semantic_role": part.semantic_role,
    })


def _read_index(root: Path) -> dict[str, Any]:
    path = root / INDEX_NAME
    if not path.exists():
        return {
            "schema": SCHEMA,
            "geometry_objects": {},
            "items": {},
            "automatic_admission": False,
        }
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ReusablePartLibraryError(f"cannot read part-library index: {exc}") from exc
    if not isinstance(value, dict) or value.get("schema") != SCHEMA:
        raise ReusablePartLibraryError("unsupported part-library index")
    if not isinstance(value.get("geometry_objects"), dict) or not isinstance(value.get("items"), dict):
        raise ReusablePartLibraryError("part-library index collections are invalid")
    if value.get("automatic_admission") is not False:
        raise ReusablePartLibraryError("part library must remain explicit-admission only")
    return value


def _object_path(root: Path, digest: str) -> Path:
    if not isinstance(digest, str) or not digest.startswith("sha256:") or len(digest) != 71:
        raise ReusablePartLibraryError("invalid geometry digest")
    return root / "objects" / f"{digest[7:]}.json"


def discover_assembly_parts(
    assembly: ConstructionAssembly,
    *,
    library_root: str | Path | None = None,
) -> dict[str, Any]:
    """Scan without mutating the source assembly or library."""
    present_geometry: set[str] = set()
    present_items: set[str] = set()
    if library_root is not None:
        root = Path(library_root)
        if root.exists():
            index = _read_index(root)
            present_geometry = set(index["geometry_objects"])
            present_items = set(index["items"])

    rows = []
    for part in assembly.parts:
        geometry = geometry_digest(part.mesh)
        item = semantic_item_digest(part)
        rows.append({
            "part_id": part.part_id,
            "geometry_sha256": geometry,
            "semantic_item_sha256": item,
            "material_family": part.material_family,
            "semantic_role": part.semantic_role,
            "already_library_geometry": geometry in present_geometry,
            "already_library_item": item in present_items,
            "topology": topology_report(part.mesh),
        })
    return {
        "schema": "axm.game-assets.reusable-part-scan/v0.1",
        "assembly": assembly.name,
        "assembly_receipt_digest": assembly.receipt.get("receipt_digest"),
        "candidate_count": len(rows),
        "candidates": rows,
        "library_mutated": False,
        "truth": (
            "Discovery only. A part remains permanent in its source asset even when "
            "it is not in the reusable library."
        ),
    }


def _write_create_or_verify(path: Path, payload: bytes) -> bool:
    """Return True when created, False when identical bytes already existed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("xb") as handle:
            handle.write(payload)
        return True
    except FileExistsError:
        existing = path.read_bytes()
        if existing != payload:
            raise ReusablePartLibraryError(
                f"content-addressed object collision/drift at {path}"
            )
        return False


def pull_assembly_parts(
    assembly: ConstructionAssembly,
    library_root: str | Path,
    selected_part_ids: Iterable[str],
) -> dict[str, Any]:
    """Explicitly admit selected parts; never scans-and-admits implicitly."""
    selected = list(dict.fromkeys(str(value) for value in selected_part_ids))
    by_id = {part.part_id: part for part in assembly.parts}
    missing = sorted(set(selected) - set(by_id))
    if missing:
        raise ReusablePartLibraryError(f"unknown selected part ids: {missing}")

    root = Path(library_root)
    root.mkdir(parents=True, exist_ok=True)
    index = _read_index(root)
    created_geometry = 0
    reused_geometry = 0
    created_items = 0
    reused_items = 0
    admitted = []

    for part_id in selected:
        part = by_id[part_id]
        geometry = geometry_digest(part.mesh)
        payload = {
            **_geometry_payload(part.mesh),
            "geometry_sha256": geometry,
        }
        object_bytes = json.dumps(
            payload, indent=2, sort_keys=True, ensure_ascii=False
        ).encode("utf-8") + b"\n"
        created = _write_create_or_verify(_object_path(root, geometry), object_bytes)
        if created:
            created_geometry += 1
        else:
            reused_geometry += 1

        index["geometry_objects"][geometry] = {
            "object": f"objects/{geometry[7:]}.json",
            "bytes": len(object_bytes),
        }

        item_id = semantic_item_digest(part)
        item_record = {
            "geometry_sha256": geometry,
            "material_family": part.material_family,
            "semantic_role": part.semantic_role,
        }
        if item_id in index["items"]:
            if index["items"][item_id] != item_record:
                raise ReusablePartLibraryError(
                    f"semantic item digest collision/drift: {item_id}"
                )
            reused_items += 1
        else:
            index["items"][item_id] = item_record
            created_items += 1

        admitted.append({
            "source_part_id": part_id,
            "geometry_sha256": geometry,
            "semantic_item_sha256": item_id,
            "geometry_created": created,
        })

    index["automatic_admission"] = False
    index["counts"] = {
        "geometry_objects": len(index["geometry_objects"]),
        "semantic_items": len(index["items"]),
    }
    index["index_digest"] = _digest({
        key: value for key, value in index.items() if key != "index_digest"
    })
    index_bytes = json.dumps(
        index, indent=2, sort_keys=True, ensure_ascii=False
    ).encode("utf-8") + b"\n"
    (root / INDEX_NAME).write_bytes(index_bytes)

    return {
        "schema": "axm.game-assets.reusable-part-pull/v0.1",
        "assembly": assembly.name,
        "selected_part_ids": selected,
        "admitted": admitted,
        "created_geometry_atoms": created_geometry,
        "reused_geometry_atoms": reused_geometry,
        "created_semantic_items": created_items,
        "reused_semantic_items": reused_items,
        "library_index_digest": index["index_digest"],
        "automatic_admission": False,
        "source_asset_mutated": False,
    }


def load_geometry_atom(library_root: str | Path, digest: str, *, name: str = "library-part") -> Mesh:
    root = Path(library_root)
    path = _object_path(root, digest)
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ReusablePartLibraryError(f"cannot load geometry atom {digest}: {exc}") from exc
    if not isinstance(value, dict) or value.get("schema") != OBJECT_SCHEMA:
        raise ReusablePartLibraryError("unsupported geometry atom")
    actual = _digest({
        "schema": OBJECT_SCHEMA,
        "vertices": value.get("vertices"),
        "faces": value.get("faces"),
        "topology": value.get("topology"),
    })
    if actual != digest or value.get("geometry_sha256") != digest:
        raise ReusablePartLibraryError("geometry atom digest mismatch")
    mesh = Mesh(
        name,
        [tuple(float(v) for v in row) for row in value["vertices"]],
        [tuple(int(v) for v in face) for face in value["faces"]],
    )
    report = topology_report(mesh)
    if report != value.get("topology"):
        raise ReusablePartLibraryError("geometry atom topology receipt drift")
    return mesh
