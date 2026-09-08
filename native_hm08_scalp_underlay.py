#!/usr/bin/env python3
"""Source-UV-preserving hm08 short-hair scalp underlay.

The laid card groom is a strand/detail layer, not enough continuous hair mass on
its own. This organ derives a thin scalp shell directly from canonical hm08 head
faces, preserves their source UVs, and offsets them outward by a bounded amount.
It is intentionally a substrate for short hair, not a hairstyle generator.
"""
from __future__ import annotations

import hashlib
import json
import random
from pathlib import Path

from native_geometry import Mesh, bounds, scale, vertex_normals
from native_hm08_face_proof import DEFAULT_WEIGHTS
from native_pbr import png_bytes
from native_targets import load_target, mix_targets
from native_uv import UVMap, read_obj_uv, validate_uv

SEED_ROOT = Path("seed_data/hm08_head_v0.2")
RAW_TO_M = 0.1
SCHEMA = "axm.game-assets.hm08-scalp-underlay.v0.1"


def _sha(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _allowed_vertex(point: tuple[float, float, float], *, eye_y: float, eye_z: float, half_width: float) -> bool:
    x, y, z = point
    ax = abs(x)
    # Upper cap: keep crown/hairline broad but stay inside the ear envelope.
    if y >= eye_y + 0.030 and ax <= half_width * 0.92:
        return True
    # Side/back cap: only behind the eye plane; this avoids painting a dark shell
    # across forehead, cheek, or outer ear while giving the laid cards a base mass.
    if y >= eye_y + 0.006 and z <= eye_z - 0.018 and ax <= half_width * 0.82:
        return True
    # Lower posterior closure is allowed a little lower, but stays well behind the
    # eye plane and inside the head width so the neck/ear remain exposed.
    if y >= eye_y - 0.012 and z <= eye_z - 0.040 and ax <= half_width * 0.80:
        return True
    return False


def build_hm08_scalp_underlay(
    head_m: Mesh,
    head_uv: UVMap,
    *,
    eye_metadata: dict[str, object],
    offset_m: float = 0.00035,
) -> tuple[Mesh, UVMap, dict[str, object]]:
    if offset_m <= 0.0 or offset_m > 0.001:
        raise ValueError("scalp underlay offset must be >0 and <=1 mm")
    if len(head_uv.face_uvs) != len(head_m.faces):
        raise ValueError("source UV face count must match head face count")

    lo, hi = bounds(head_m)
    half_width = max(abs(lo[0]), abs(hi[0]), 1e-9)
    eye_y = sum(float(eye_metadata["eyes"][side]["center_m"][1]) for side in ("left", "right")) * 0.5
    eye_z = sum(float(eye_metadata["eyes"][side]["center_m"][2]) for side in ("left", "right")) * 0.5
    normals = vertex_normals(head_m)

    selected_faces: list[int] = []
    for face_index, face in enumerate(head_m.faces):
        # Requiring every face vertex to be inside the scalp field prevents a
        # centroid-only face from crossing the intended hairline/ear boundary.
        if face and all(_allowed_vertex(head_m.vertices[i], eye_y=eye_y, eye_z=eye_z, half_width=half_width) for i in face):
            selected_faces.append(face_index)
    if not selected_faces:
        raise ValueError("hm08 scalp underlay selected no faces")

    used_vertices = sorted({i for face_index in selected_faces for i in head_m.faces[face_index]})
    remap = {old: new for new, old in enumerate(used_vertices)}
    vertices = []
    for old in used_vertices:
        x, y, z = head_m.vertices[old]
        nx, ny, nz = normals[old]
        vertices.append((x + nx * offset_m, y + ny * offset_m, z + nz * offset_m))
    faces = [tuple(remap[i] for i in head_m.faces[face_index]) for face_index in selected_faces]
    shell = Mesh("sentinel_hm08_short_hair_underlay", vertices, faces)

    # Preserve the original hm08 face-varying UVs exactly for every retained face.
    uvs: list[tuple[float, float]] = []
    face_uvs: list[tuple[int, ...]] = []
    for face_index in selected_faces:
        refs: list[int] = []
        for source_uv_index in head_uv.face_uvs[face_index]:
            refs.append(len(uvs))
            uvs.append(head_uv.uvs[source_uv_index])
        face_uvs.append(tuple(refs))
    shell_uv = UVMap(uvs, face_uvs, "hm08_source_uv_scalp_underlay")
    uv_report = validate_uv(shell, shell_uv)
    if uv_report["status"] != "pass":
        raise ValueError(f"hm08 scalp underlay UV invalid: {uv_report}")

    xs = [p[0] for p in shell.vertices]
    ys = [p[1] for p in shell.vertices]
    zs = [p[2] for p in shell.vertices]
    evidence: dict[str, object] = {
        "schema": SCHEMA,
        "source_face_count": len(head_m.faces),
        "selected_face_count": len(selected_faces),
        "selected_vertex_count": len(used_vertices),
        "offset_m": offset_m,
        "eye_y_m": eye_y,
        "eye_z_m": eye_z,
        "half_width_m": half_width,
        "x_range_m": [min(xs), max(xs)],
        "y_range_m": [min(ys), max(ys)],
        "z_range_m": [min(zs), max(zs)],
        "uv_validation": uv_report,
        "truth": {
            "source_grounded": True,
            "source_uv_preserved": True,
            "role": "continuous_short_hair_root_mass_beneath_cards",
            "preferred_claim": False,
            "notes": [
                "The shell is derived only from retained hm08 head faces; it is not a guessed helmet primitive.",
                "The 0.35 mm default offset avoids coplanar z-fighting while remaining a bounded scalp substrate.",
                "Visual promotion still requires the real Godot face views."
            ],
        },
    }
    return shell, shell_uv, evidence


def write_scalp_underlay_material(
    root: str | Path,
    *,
    size: int = 128,
    seed: int = 82081,
) -> dict[str, object]:
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    rng = random.Random(seed)
    base = bytearray()
    normal = bytes((128, 128, 255)) * (size * size)
    orm = bytearray()
    for _ in range(size * size):
        grain = rng.randint(-5, 5)
        base.extend((max(0, 24 + grain), max(0, 16 + grain), max(0, 12 + grain)))
        roughness = max(0, min(255, 186 + rng.randint(-8, 8)))
        orm.extend((255, roughness, 0))
    files = {
        "base_color": ("base_color.png", png_bytes(size, size, 3, bytes(base))),
        "normal": ("normal.png", png_bytes(size, size, 3, normal)),
        "orm": ("orm.png", png_bytes(size, size, 3, bytes(orm))),
    }
    maps: dict[str, dict[str, str]] = {}
    for name, (filename, data) in files.items():
        (root / filename).write_bytes(data)
        maps[name] = {"path": filename, "sha256": _sha(data)}
    return {
        "schema": "axm.game-assets.scalp-underlay-material.v0.1",
        "seed": seed,
        "size": size,
        "maps": maps,
        "pbr": {"metallic_factor": 0.0, "roughness_role": "dense short-hair root mass"},
    }


def build_preferred_hm08_scalp_underlay():
    raw_head, head_uv = read_obj_uv(SEED_ROOT / "head.obj", name="hm08_head_v0_2")
    library = {
        name: load_target(SEED_ROOT / "targets" / f"{name}.target", license="CC0-source-remap")
        for name in sorted(DEFAULT_WEIGHTS)
    }
    identity, _ = mix_targets(raw_head, library, DEFAULT_WEIGHTS, name="sentinel_identity_for_scalp_underlay")
    head_m = scale(identity, RAW_TO_M, name="sentinel_identity_scalp_underlay_m")
    eye_metadata = json.loads((SEED_ROOT / "eye-landmarks.json").read_text(encoding="utf-8"))
    return build_hm08_scalp_underlay(head_m, head_uv, eye_metadata=eye_metadata)


if __name__ == "__main__":
    _, _, evidence = build_preferred_hm08_scalp_underlay()
    print(json.dumps(evidence, indent=2, sort_keys=True))
