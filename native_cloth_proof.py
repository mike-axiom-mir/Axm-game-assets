#!/usr/bin/env python3
"""AXM native cloth motion/material/delivery proof v0.1."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from native_cloth import SphereCollider, cloth_evidence, copy_cloth, make_cloth_grid, simulate_cloth
from native_fabric_material import write_fabric_material
from native_gltf import write_gltf
from native_preview import write_preview
from native_uv import UVMap, validate_uv

SCHEMA = "axm.game-assets.native-cloth-proof.v0.1"


def _sha(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def rest_planar_uv(system) -> UVMap:
    vertices = system.positions
    xs = [point[0] for point in vertices]
    zs = [point[2] for point in vertices]
    lo_x, hi_x = min(xs), max(xs)
    lo_z, hi_z = min(zs), max(zs)
    span_x = max(hi_x - lo_x, 1e-12)
    span_z = max(hi_z - lo_z, 1e-12)
    uvs = [((point[0] - lo_x) / span_x, (point[2] - lo_z) / span_z) for point in vertices]
    return UVMap(uvs, [tuple(face) for face in system.mesh.faces], "cloth_rest_xz")


def _view(preview, name):
    return next(item for item in preview["views"] if item["view"] == name)


def build_cloth_proof(output: str | Path, *, steps: int = 120, seed: int = 515, texture_size: int = 64, preview_size: int = 96) -> dict[str, object]:
    root = Path(output)
    root.mkdir(parents=True, exist_ok=True)
    system = make_cloth_grid(0.8, 0.8, columns=12, rows=12, height=0.55, name="sentinel_cloth_fixture")
    deterministic_twin = copy_cloth(system)
    uvmap = rest_planar_uv(system)
    collider = SphereCollider((0.0, 0.0, 0.0), 0.22)

    rest_preview = write_preview(system.mesh, root / "preview-rest", size=preview_size)
    simulate_cloth(system, steps=steps, dt=1.0 / 60.0, iterations=10, colliders=[collider])
    simulate_cloth(deterministic_twin, steps=steps, dt=1.0 / 60.0, iterations=10, colliders=[collider])
    deterministic = system.positions == deterministic_twin.positions
    evidence = cloth_evidence(system, colliders=[collider])
    uv_report = validate_uv(system.mesh, uvmap)
    final_preview = write_preview(system.mesh, root / "preview-final", size=preview_size)

    material = write_fabric_material(root / "textures", size=texture_size, seed=seed)
    delivery = write_gltf(
        system.mesh,
        uvmap,
        root,
        material_name="AXM_Native_WovenFabric",
        double_sided=True,
    )

    rest_side = _view(rest_preview, "side")
    final_side = _view(final_preview, "side")
    rest_front = _view(rest_preview, "front")
    final_front = _view(final_preview, "front")
    manifest: dict[str, object] = {
        "schema": SCHEMA,
        "asset": "sentinel-cloth-secondary-motion-fixture",
        "simulation": {
            "steps": steps,
            "dt": 1.0 / 60.0,
            "solver_iterations": 10,
            "collider": {"center": list(collider.center), "radius": collider.radius},
            "evidence": evidence,
            "deterministic_twin_match": deterministic,
        },
        "uv": uv_report,
        "material": material,
        "delivery": delivery,
        "preview": {"rest": rest_preview, "final": final_preview},
        "acceptance": {
            "deterministic_motion": deterministic,
            "pins_stable": evidence["max_pin_drift"] == 0.0,
            "collision_clear": evidence["max_sphere_penetration"] < 1e-8,
            "stretch_within_fixture_budget": evidence["max_constraint_strain"] < 0.04,
            "cloth_moved_under_gravity": evidence["bounds_y"][0] < 0.0,
            "uv_valid_after_deformation": uv_report["status"] == "pass",
            "side_geometry_signal_changed": rest_side["hashes"]["silhouette"] != final_side["hashes"]["silhouette"],
            "front_depth_signal_changed": rest_front["hashes"]["depth"] != final_front["hashes"]["depth"],
            "gltf_structural_valid": delivery["validation"]["status"] == "pass",
            "fabric_material_identity": delivery["material_name"] == "AXM_Native_WovenFabric" and delivery["double_sided"] is True,
        },
        "truth": {
            "production_garment_claim": False,
            "notes": [
                "This proves deterministic cloth state, rest UVs, fabric material, secondary motion, collision and snapshot delivery on a fixture.",
                "It does not prove tailoring, self-collision, friction, aerodynamics, seam quality or final garment aesthetics.",
                "Snapshot glTF contains the deformed cloth mesh; persistent runtime cloth constraints remain AXM source state rather than glTF animation in v0.1.",
            ],
        },
    }
    payload = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8")
    (root / "cloth-proof.json").write_bytes(payload)
    manifest["manifest_sha256"] = _sha(payload)
    return manifest
