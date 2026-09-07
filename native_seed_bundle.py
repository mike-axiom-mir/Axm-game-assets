#!/usr/bin/env python3
"""Receipt-bearing importer for fixed-topology seed mesh + sparse target bundles."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Mapping, Sequence

from native_geometry import read_obj, write_obj
from native_parametric import build_variant, rebuild_variant
from native_targets import SparseTarget, load_target, target_digest

SCHEMA = "axm.game-assets.seed-bundle.v0.1"


def _sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def build_seed_bundle(
    base_obj: str | Path,
    target_files: Sequence[str | Path],
    weights: Mapping[str, float],
    output: str | Path,
    *,
    seed_id: str,
    basemesh_id: str | None = None,
    seed_source: str | None = None,
    declared_license: str | None = None,
    license_evidence: str | None = None,
    unit_meters: float | None = None,
) -> dict[str, object]:
    base_path = Path(base_obj)
    if not base_path.exists():
        raise FileNotFoundError(base_path)
    root = Path(output)
    root.mkdir(parents=True, exist_ok=True)

    mesh = read_obj(base_path, name=seed_id)
    library: dict[str, SparseTarget] = {}
    target_receipts = []
    for raw_path in target_files:
        path = Path(raw_path)
        if not path.exists():
            raise FileNotFoundError(path)
        target = load_target(path, source=path.as_posix(), license=declared_license)
        target_basemesh = target.metadata.get("basemesh")
        if basemesh_id and target_basemesh and target_basemesh != basemesh_id:
            raise ValueError(f"target {target.name} expects basemesh {target_basemesh!r}, required {basemesh_id!r}")
        if target.name in library:
            raise ValueError(f"duplicate target name {target.name!r}")
        library[target.name] = target
        target_receipts.append({
            "name": target.name,
            "file": path.as_posix(),
            "file_sha256": _sha256(path),
            "target_digest": target_digest(target),
            "basemesh": target_basemesh,
            "rows": len(target.deltas),
            "declared_license": declared_license,
        })

    variant = build_variant(
        mesh,
        library,
        weights,
        seed_id=seed_id,
        seed_source=seed_source or base_path.as_posix(),
        seed_license=declared_license,
        unit_meters=unit_meters,
        name=f"{seed_id}_variant",
    )
    # Prove the recorded state can reconstruct before emitting it.
    rebuilt = rebuild_variant(mesh, library, variant.state)
    if rebuilt.mesh.vertices != variant.mesh.vertices or rebuilt.mesh.faces != variant.mesh.faces:
        raise AssertionError("seed bundle reconstruction proof failed")

    write_obj(mesh, root / "seed.obj", include_normals=False)
    write_obj(variant.mesh, root / "variant.obj", include_normals=True)
    (root / "parametric-state.json").write_text(json.dumps(variant.state, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    manifest: dict[str, object] = {
        "schema": SCHEMA,
        "seed": {
            "id": seed_id,
            "basemesh_id": basemesh_id,
            "source_file": base_path.as_posix(),
            "source_sha256": _sha256(base_path),
            "source": seed_source,
            "declared_license": declared_license,
            "license_evidence": license_evidence,
            "vertices": len(mesh.vertices),
            "faces": len(mesh.faces),
            "unit_meters": unit_meters,
        },
        "targets": target_receipts,
        "weights": {name: float(weights[name]) for name in sorted(weights)},
        "parametric_state_digest": variant.state["state_digest"],
        "outputs": {
            "seed_obj_sha256": _sha256(root / "seed.obj"),
            "variant_obj_sha256": _sha256(root / "variant.obj"),
            "state_sha256": _sha256(root / "parametric-state.json"),
        },
        "acceptance": {
            "reconstruction_exact": True,
            "topology_preserved": variant.state["truth"]["topology_preserved"],
            "all_requested_targets_present": set(weights).issubset(library),
        },
        "truth": {
            "license_verified_by_code": False,
            "notes": [
                "License/source fields are preserved evidence supplied to the importer; this code does not perform legal verification.",
                "Basemesh compatibility is checked when a target file declares '# basemesh <id>' and the caller supplies basemesh_id.",
                "Exact reconstruction is proven against the hashed seed and target state before output is accepted.",
            ],
        },
    }
    manifest_bytes = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8")
    (root / "seed-bundle.json").write_bytes(manifest_bytes)
    manifest["manifest_sha256"] = "sha256:" + hashlib.sha256(manifest_bytes).hexdigest()
    return manifest
