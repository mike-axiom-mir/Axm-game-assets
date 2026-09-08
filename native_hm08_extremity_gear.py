#!/usr/bin/env python3
"""Source-derived Sentinel gloves and boots over the complete hm08 body.

The human body remains canonical skin. This organ derives a fitted textile shell
for distal hands and boot uppers from the same body topology/UVs, offsets it by
a bounded physical clearance, and adds deterministic rubber soles as separate
closed constructive geometry. The output is editable gear state, not a baked
mutation of the character mesh.
"""
from __future__ import annotations

import hashlib
import json
from math import sqrt
from pathlib import Path

from native_fabric_material import FabricSpec, write_fabric_material
from native_geometry import Mesh, bounds, combine, scale, topology_report, vertex_normals
from native_hm08_face_proof import DEFAULT_WEIGHTS
from native_modeling import make_chamfered_box, place
from native_pbr import png_bytes
from native_targets import load_target, mix_targets
from native_uv import UVMap, box_project_world, read_obj_uv, validate_uv

FULL_SEED = Path("seed_data/hm08_full_body_v0.1")
RAW_TO_M = 0.1
SCHEMA = "axm.game-assets.hm08-extremity-gear.v0.1"


def _tri_area(a, b, c) -> float:
    ab = (b[0]-a[0], b[1]-a[1], b[2]-a[2])
    ac = (c[0]-a[0], c[1]-a[1], c[2]-a[2])
    cross = (
        ab[1]*ac[2] - ab[2]*ac[1],
        ab[2]*ac[0] - ab[0]*ac[2],
        ab[0]*ac[1] - ab[1]*ac[0],
    )
    return 0.5 * sqrt(cross[0]**2 + cross[1]**2 + cross[2]**2)


def _face_area(mesh: Mesh, face: tuple[int, ...]) -> float:
    if len(face) < 3:
        return 0.0
    root = mesh.vertices[face[0]]
    return sum(_tri_area(root, mesh.vertices[face[i]], mesh.vertices[face[i+1]]) for i in range(1, len(face)-1))


def _load_identity_body() -> tuple[Mesh, UVMap, dict[str, object]]:
    raw, uv = read_obj_uv(FULL_SEED / "body.obj", name="hm08_full_body_v0_1")
    library = {
        name: load_target(FULL_SEED / "targets" / f"{name}.target", license="CC0-source-remap")
        for name in sorted(DEFAULT_WEIGHTS)
    }
    identity, state = mix_targets(raw, library, DEFAULT_WEIGHTS, name="sentinel_full_body_identity_for_extremity_gear")
    return scale(identity, RAW_TO_M, name="sentinel_full_body_identity_m_for_extremity_gear"), uv, state


def _subset_shell(
    body_m: Mesh,
    body_uv: UVMap,
    selected_faces: list[int],
    *,
    offset_m: float,
    name: str,
) -> tuple[Mesh, UVMap]:
    if not selected_faces:
        raise ValueError(f"{name} selected no source faces")
    normals = vertex_normals(body_m)
    used_vertices = sorted({index for face_index in selected_faces for index in body_m.faces[face_index]})
    remap = {source: compact for compact, source in enumerate(used_vertices)}
    vertices = []
    for source in used_vertices:
        x, y, z = body_m.vertices[source]
        nx, ny, nz = normals[source]
        vertices.append((x + nx * offset_m, y + ny * offset_m, z + nz * offset_m))
    faces = [tuple(remap[index] for index in body_m.faces[face_index]) for face_index in selected_faces]
    shell = Mesh(name, vertices, faces)

    uvs: list[tuple[float, float]] = []
    face_uvs: list[tuple[int, ...]] = []
    for face_index in selected_faces:
        refs: list[int] = []
        for source_uv in body_uv.face_uvs[face_index]:
            refs.append(len(uvs))
            uvs.append(body_uv.uvs[source_uv])
        face_uvs.append(tuple(refs))
    uvmap = UVMap(uvs, face_uvs, f"hm08_source_uv_{name}")
    report = validate_uv(shell, uvmap)
    if report["status"] != "pass":
        raise ValueError(f"{name} UV invalid: {report}")
    return shell, uvmap


def build_hm08_extremity_gear(
    body_m: Mesh,
    body_uv: UVMap,
    *,
    shell_offset_m: float = 0.0024,
    glove_lateral_fraction: float = 0.79,
    boot_height_fraction: float = 0.10,
) -> tuple[Mesh, UVMap, Mesh, UVMap, dict[str, object]]:
    if not (0.001 <= shell_offset_m <= 0.005):
        raise ValueError("extremity shell offset must be within 1-5 mm")
    if len(body_uv.face_uvs) != len(body_m.faces):
        raise ValueError("body UV face count must match body faces")

    lo, hi = bounds(body_m)
    height = hi[1] - lo[1]
    half_width = max(abs(lo[0]), abs(hi[0]), 1e-9)
    glove_inner_x = half_width * glove_lateral_fraction
    boot_top_y = lo[1] + height * boot_height_fraction

    glove_faces: list[int] = []
    boot_faces: list[int] = []
    for face_index, face in enumerate(body_m.faces):
        points = [body_m.vertices[index] for index in face]
        if points and all(abs(point[0]) >= glove_inner_x for point in points):
            glove_faces.append(face_index)
        if points and all(point[1] <= boot_top_y for point in points):
            boot_faces.append(face_index)

    selected_faces = sorted(set(glove_faces) | set(boot_faces))
    shell, shell_uv = _subset_shell(
        body_m,
        body_uv,
        selected_faces,
        offset_m=shell_offset_m,
        name="sentinel_glove_boot_upper_shell_v0_1",
    )
    shell_topology = topology_report(shell)
    shell_uv_report = validate_uv(shell, shell_uv)

    # Soles are separate closed rigid-rubber geometry so the boot has a real
    # game silhouette rather than reading as a painted sock over the human foot.
    foot_points = [point for point in body_m.vertices if point[1] <= boot_top_y]
    if not foot_points:
        raise ValueError("boot region has no foot points")
    side_reports = {}
    sole_parts: list[Mesh] = []
    for side, sign in (("left", -1.0), ("right", 1.0)):
        side_points = [point for point in foot_points if point[0] * sign > 0.0]
        if not side_points:
            raise ValueError(f"{side} boot has no side points")
        xs = [p[0] for p in side_points]
        zs = [p[2] for p in side_points]
        x_min, x_max = min(xs), max(xs)
        z_min, z_max = min(zs), max(zs)
        width = (x_max - x_min) + 0.018
        depth = (z_max - z_min) + 0.026
        x_center = (x_min + x_max) * 0.5
        z_center = (z_min + z_max) * 0.5 + 0.006
        sole_height = 0.026
        sole = make_chamfered_box(width, sole_height, depth, min(0.018, width * 0.16), name=f"{side}_boot_sole")
        sole = place(sole, x=x_center, y=lo[1] - sole_height * 0.34, z=z_center, name=f"{side}_boot_sole")
        sole_parts.append(sole)
        side_reports[side] = {
            "x_center_m": x_center,
            "z_center_m": z_center,
            "width_m": width,
            "depth_m": depth,
            "height_m": sole_height,
        }

    soles = combine(sole_parts, name="sentinel_boot_soles_v0_1")
    sole_uv = box_project_world(soles, world_units_per_tile=0.08)
    sole_uv_report = validate_uv(soles, sole_uv)
    sole_topology = topology_report(soles)
    if sole_uv_report["status"] != "pass":
        raise ValueError(f"boot sole UV invalid: {sole_uv_report}")
    if sole_topology["invalid_indices"] or sole_topology["degenerate_faces"] or sole_topology["nonmanifold_edges"]:
        raise ValueError(f"boot sole topology invalid: {sole_topology}")

    source_area = sum(_face_area(body_m, face) for face in body_m.faces)
    glove_area = sum(_face_area(body_m, body_m.faces[index]) for index in glove_faces)
    boot_area = sum(_face_area(body_m, body_m.faces[index]) for index in boot_faces)
    evidence: dict[str, object] = {
        "schema": SCHEMA,
        "source_body_vertices": len(body_m.vertices),
        "source_body_faces": len(body_m.faces),
        "source_surface_area_m2": source_area,
        "shell_face_count": len(selected_faces),
        "glove_face_count": len(glove_faces),
        "boot_upper_face_count": len(boot_faces),
        "glove_source_area_m2": glove_area,
        "boot_upper_source_area_m2": boot_area,
        "shell_offset_m": shell_offset_m,
        "selection": {
            "glove_inner_abs_x_m": glove_inner_x,
            "glove_lateral_fraction": glove_lateral_fraction,
            "boot_top_y_m": boot_top_y,
            "boot_height_fraction": boot_height_fraction,
        },
        "shell_topology": shell_topology,
        "shell_uv_validation": shell_uv_report,
        "sole_topology": sole_topology,
        "sole_uv_validation": sole_uv_report,
        "sole_components": side_reports,
        "truth": {
            "source_grounded": True,
            "source_uv_preserved": True,
            "canonical_body_mutated": False,
            "production_glove_claim": False,
            "production_boot_claim": False,
            "notes": [
                "Glove and boot-upper shells are selected from the complete pinned human surface and offset outward without modifying canonical body vertices.",
                "Rubber soles are separate closed constructive geometry and therefore remain independently replaceable/editable.",
                "This pass removes bare-hand/bare-foot prototype read; production gloves/boots still need seam/panel detail, finger articulation, sole tread and deformation evidence."
            ],
        },
    }
    return shell, shell_uv, soles, sole_uv, evidence


def _sha(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _write_rubber_material(output: Path, *, size: int) -> dict[str, object]:
    output.mkdir(parents=True, exist_ok=True)
    base = png_bytes(size, size, 3, bytes((13, 16, 18)) * (size * size))
    normal = png_bytes(size, size, 3, bytes((128, 128, 255)) * (size * size))
    rough = 224
    orm = png_bytes(size, size, 3, bytes((255, rough, 0)) * (size * size))
    receipts = {}
    for name, data in (("base_color.png", base), ("normal.png", normal), ("orm.png", orm)):
        (output / name).write_bytes(data)
        receipts[name] = _sha(data)
    return {
        "schema": "axm.game-assets.tactical-rubber.v0.1",
        "maps": receipts,
        "metalness": 0.0,
        "roughness": rough / 255.0,
        "truth": {"deterministic": True, "production_rubber_claim": False},
    }


def write_sentinel_extremity_materials(output: str | Path, *, size: int = 256, seed: int = 95021) -> dict[str, object]:
    root = Path(output)
    textile = write_fabric_material(
        root / "textile",
        size=size,
        seed=seed,
        spec=FabricSpec(
            base_rgb=(18, 23, 26),
            warp_threads=76,
            weft_threads=70,
            weave_depth=0.055,
            roughness=0.70,
            fiber_noise=0.060,
            thickness_hint_mm=1.6,
        ),
    )
    rubber = _write_rubber_material(root / "rubber", size=size)
    return {
        "schema": "axm.game-assets.sentinel-extremity-materials.v0.1",
        "textile": textile,
        "rubber": rubber,
    }


def build_preferred_hm08_extremity_gear():
    body_m, body_uv, _state = _load_identity_body()
    return build_hm08_extremity_gear(body_m, body_uv)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("output", nargs="?", default="build/hm08-extremity-gear")
    parser.add_argument("--texture-size", type=int, default=256)
    args = parser.parse_args()
    body_m, body_uv, target_state = _load_identity_body()
    shell, shell_uv, soles, sole_uv, evidence = build_hm08_extremity_gear(body_m, body_uv)
    materials = write_sentinel_extremity_materials(Path(args.output) / "textures", size=args.texture_size)
    Path(args.output).mkdir(parents=True, exist_ok=True)
    packet = {
        "evidence": evidence,
        "target_state": target_state,
        "materials": materials,
        "shell": {"vertices": len(shell.vertices), "faces": len(shell.faces), "uvs": len(shell_uv.uvs)},
        "soles": {"vertices": len(soles.vertices), "faces": len(soles.faces), "uvs": len(sole_uv.uvs)},
    }
    (Path(args.output) / "extremity-gear.json").write_text(json.dumps(packet, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(packet, indent=2))
