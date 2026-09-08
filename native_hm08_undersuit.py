#!/usr/bin/env python3
"""Source-derived Sentinel undersuit shell over the pinned complete hm08 body.

The undersuit is a fitted garment substrate, not painted body skin. It retains
selected canonical body faces and their source UVs, offsets them outward by a
bounded physical amount, and deliberately leaves head, hands and feet exposed.
It is intended to become the soft layer underneath rigid Sentinel armor.
"""
from __future__ import annotations

import json
from pathlib import Path

from native_fabric_material import FabricSpec, write_fabric_material
from native_geometry import Mesh, scale, topology_report, vertex_normals
from native_hm08_face_proof import DEFAULT_WEIGHTS
from native_targets import load_target, mix_targets
from native_uv import UVMap, read_obj_uv, validate_uv

FULL_SEED = Path("seed_data/hm08_full_body_v0.1")
RAW_TO_M = 0.1
SCHEMA = "axm.game-assets.hm08-undersuit.v0.1"


def _load_identity_body() -> tuple[Mesh, UVMap, dict[str, object]]:
    raw, uv = read_obj_uv(FULL_SEED / "body.obj", name="hm08_full_body_v0_1")
    library = {
        name: load_target(FULL_SEED / "targets" / f"{name}.target", license="CC0-source-remap")
        for name in sorted(DEFAULT_WEIGHTS)
    }
    identity, state = mix_targets(raw, library, DEFAULT_WEIGHTS, name="sentinel_full_body_identity_for_undersuit")
    return scale(identity, RAW_TO_M, name="sentinel_full_body_identity_m_for_undersuit"), uv, state


def _is_suit_vertex(
    point: tuple[float, float, float],
    *,
    collar_y_m: float,
    ankle_y_m: float,
    wrist_abs_x_m: float,
) -> bool:
    x, y, _z = point
    return y <= collar_y_m and y >= ankle_y_m and abs(x) <= wrist_abs_x_m


def build_hm08_undersuit(
    body_m: Mesh,
    body_uv: UVMap,
    *,
    offset_m: float = 0.0022,
    collar_y_m: float = 0.565,
    ankle_y_m: float = -0.690,
    wrist_abs_x_m: float = 0.405,
) -> tuple[Mesh, UVMap, dict[str, object]]:
    if offset_m <= 0.0 or offset_m > 0.006:
        raise ValueError("undersuit offset must be >0 and <=6 mm")
    if len(body_uv.face_uvs) != len(body_m.faces):
        raise ValueError("body UV face count must match body faces")

    selected_faces: list[int] = []
    for face_index, face in enumerate(body_m.faces):
        if face and all(
            _is_suit_vertex(
                body_m.vertices[index],
                collar_y_m=collar_y_m,
                ankle_y_m=ankle_y_m,
                wrist_abs_x_m=wrist_abs_x_m,
            )
            for index in face
        ):
            selected_faces.append(face_index)
    if len(selected_faces) < 4000:
        raise ValueError(f"undersuit selected too little body surface: {len(selected_faces)} faces")

    normals = vertex_normals(body_m)
    used_vertices = sorted({index for face_index in selected_faces for index in body_m.faces[face_index]})
    remap = {source: compact for compact, source in enumerate(used_vertices)}
    vertices = []
    for source in used_vertices:
        x, y, z = body_m.vertices[source]
        nx, ny, nz = normals[source]
        vertices.append((x + nx * offset_m, y + ny * offset_m, z + nz * offset_m))
    faces = [tuple(remap[index] for index in body_m.faces[face_index]) for face_index in selected_faces]
    shell = Mesh("sentinel_fitted_undersuit_v0_1", vertices, faces)

    uvs: list[tuple[float, float]] = []
    face_uvs: list[tuple[int, ...]] = []
    for face_index in selected_faces:
        refs: list[int] = []
        for source_uv_index in body_uv.face_uvs[face_index]:
            refs.append(len(uvs))
            uvs.append(body_uv.uvs[source_uv_index])
        face_uvs.append(tuple(refs))
    shell_uv = UVMap(uvs, face_uvs, "hm08_source_uv_undersuit")
    uv_report = validate_uv(shell, shell_uv)
    if uv_report["status"] != "pass":
        raise ValueError(f"undersuit UV invalid: {uv_report}")

    topology = topology_report(shell)
    xs = [point[0] for point in shell.vertices]
    ys = [point[1] for point in shell.vertices]
    zs = [point[2] for point in shell.vertices]
    evidence: dict[str, object] = {
        "schema": SCHEMA,
        "source_body_vertices": len(body_m.vertices),
        "source_body_faces": len(body_m.faces),
        "selected_face_count": len(selected_faces),
        "selected_vertex_count": len(used_vertices),
        "offset_m": offset_m,
        "cuts": {
            "collar_y_m": collar_y_m,
            "ankle_y_m": ankle_y_m,
            "wrist_abs_x_m": wrist_abs_x_m,
        },
        "bounds_m": {
            "x": [min(xs), max(xs)],
            "y": [min(ys), max(ys)],
            "z": [min(zs), max(zs)],
        },
        "topology": topology,
        "uv_validation": uv_report,
        "truth": {
            "source_grounded": True,
            "source_uv_preserved": True,
            "garment_role": "fitted_soft_layer_under_rigid_armor",
            "production_tailoring_claim": False,
            "notes": [
                "The shell is derived from the complete pinned CC0 hm08 body and does not alter canonical skin geometry.",
                "Open collar, wrist and ankle boundaries are intentional garment openings, not body-topology damage.",
                "The first fitted shell establishes clothing separation and armor clearance; production tailoring still needs seam/panel logic, wrinkles and deformation evidence."
            ],
        },
    }
    return shell, shell_uv, evidence


def build_preferred_hm08_undersuit():
    body_m, body_uv, _ = _load_identity_body()
    return build_hm08_undersuit(body_m, body_uv)


def write_sentinel_undersuit_material(output: str | Path, *, size: int = 256, seed: int = 91021) -> dict[str, object]:
    return write_fabric_material(
        output,
        size=size,
        seed=seed,
        spec=FabricSpec(
            base_rgb=(25, 31, 34),
            warp_threads=72,
            weft_threads=68,
            weave_depth=0.075,
            roughness=0.64,
            fiber_noise=0.075,
            thickness_hint_mm=1.4,
        ),
    )


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("output", nargs="?", default="build/hm08-undersuit")
    parser.add_argument("--texture-size", type=int, default=256)
    args = parser.parse_args()
    body_m, body_uv, target_state = _load_identity_body()
    mesh, uv, evidence = build_hm08_undersuit(body_m, body_uv)
    material = write_sentinel_undersuit_material(Path(args.output) / "material", size=args.texture_size)
    Path(args.output).mkdir(parents=True, exist_ok=True)
    packet = {"evidence": evidence, "target_state": target_state, "material": material, "mesh_vertices": len(mesh.vertices), "mesh_faces": len(mesh.faces), "uv_count": len(uv.uvs)}
    (Path(args.output) / "undersuit.json").write_text(json.dumps(packet, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(packet, indent=2))
