#!/usr/bin/env python3
"""Geometry-grounded semantic skin bake for repaired hm08 human head state.

This organ does not use a scan, proprietary face labels, or an external DCC.
It rasterizes the canonical hm08 head into its preserved UV map, derives a few
stable facial landmarks from geometry/source metadata, and modulates AXM's
procedural skin channels by semantic region. The output remains authored CG
skin, not measured physiology.
"""
from __future__ import annotations

import hashlib
import json
import math
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from native_geometry import Mesh, Vec3, bounds
from native_pbr import png_bytes
from native_skin_material import SkinMaterialSpec, skin_fields
from native_uv import UVMap, read_obj_uv, validate_uv

SEED_ROOT = Path("seed_data/hm08_head_v0.2")
SCHEMA = "axm.game-assets.hm08-semantic-skin.v0.1"


@dataclass(frozen=True, slots=True)
class FaceLandmarks:
    mouth_center: Vec3
    mouth_boundary_vertices: int
    nose_tip: Vec3
    left_eye: Vec3
    right_eye: Vec3
    bounds_min: Vec3
    bounds_max: Vec3


def _sha(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def _smoothstep(edge0: float, edge1: float, value: float) -> float:
    if abs(edge1 - edge0) <= 1e-12:
        return 0.0
    t = _clamp01((value - edge0) / (edge1 - edge0))
    return t * t * (3.0 - 2.0 * t)


def _gaussian2(x: float, y: float, cx: float, cy: float, sx: float, sy: float) -> float:
    sx = max(abs(sx), 1e-9)
    sy = max(abs(sy), 1e-9)
    dx = (x - cx) / sx
    dy = (y - cy) / sy
    return math.exp(-0.5 * (dx * dx + dy * dy))


def _boundary_components(mesh: Mesh) -> list[list[int]]:
    counts: dict[tuple[int, int], int] = defaultdict(int)
    for face in mesh.faces:
        for index, a in enumerate(face):
            b = face[(index + 1) % len(face)]
            counts[(a, b) if a < b else (b, a)] += 1
    adjacency: dict[int, set[int]] = defaultdict(set)
    for (a, b), count in counts.items():
        if count != 1:
            continue
        adjacency[a].add(b)
        adjacency[b].add(a)
    seen: set[int] = set()
    components: list[list[int]] = []
    for start in sorted(adjacency):
        if start in seen:
            continue
        stack = [start]
        seen.add(start)
        component = []
        while stack:
            current = stack.pop()
            component.append(current)
            for neighbor in adjacency[current]:
                if neighbor not in seen:
                    seen.add(neighbor)
                    stack.append(neighbor)
        components.append(component)
    return components


def derive_face_landmarks(mesh: Mesh, eye_landmarks: dict[str, object]) -> FaceLandmarks:
    components = _boundary_components(mesh)
    if len(components) < 2:
        raise ValueError("hm08 semantic skin expects neck and mouth boundary components")
    # The mouth is the front-most open component. This avoids encoding source
    # vertex ids while remaining stable under the compact v0.2 remap.
    mouth_component = max(
        components,
        key=lambda component: sum(mesh.vertices[index][2] for index in component) / len(component),
    )
    mouth_center = tuple(
        sum(mesh.vertices[index][axis] for index in mouth_component) / len(mouth_component)
        for axis in range(3)
    )
    nose_tip = max(mesh.vertices, key=lambda vertex: vertex[2])
    left_eye = tuple(float(value) for value in eye_landmarks["eyes"]["left"]["center_raw"])
    right_eye = tuple(float(value) for value in eye_landmarks["eyes"]["right"]["center_raw"])
    lo, hi = bounds(mesh)
    return FaceLandmarks(
        mouth_center=mouth_center,  # type: ignore[arg-type]
        mouth_boundary_vertices=len(mouth_component),
        nose_tip=nose_tip,
        left_eye=left_eye,  # type: ignore[arg-type]
        right_eye=right_eye,  # type: ignore[arg-type]
        bounds_min=lo,
        bounds_max=hi,
    )


def _uv_triangles(mesh: Mesh, uvmap: UVMap):
    for face, uvface in zip(mesh.faces, uvmap.face_uvs):
        if len(face) < 3 or len(face) != len(uvface):
            continue
        for corner in range(1, len(face) - 1):
            yield (
                (face[0], face[corner], face[corner + 1]),
                (uvface[0], uvface[corner], uvface[corner + 1]),
            )


def _edge(ax: float, ay: float, bx: float, by: float, px: float, py: float) -> float:
    return (px - ax) * (by - ay) - (py - ay) * (bx - ax)


def _raster_positions(mesh: Mesh, uvmap: UVMap, size: int) -> tuple[list[Vec3 | None], int]:
    positions: list[Vec3 | None] = [None] * (size * size)
    covered = 0
    for vertex_ids, uv_ids in _uv_triangles(mesh, uvmap):
        uv = [uvmap.uvs[index] for index in uv_ids]
        screen = [(u * (size - 1), v * (size - 1)) for u, v in uv]
        (ax, ay), (bx, by), (cx, cy) = screen
        area = _edge(ax, ay, bx, by, cx, cy)
        if abs(area) <= 1e-12:
            continue
        lo_x = max(0, int(math.floor(min(ax, bx, cx))))
        hi_x = min(size - 1, int(math.ceil(max(ax, bx, cx))))
        lo_y = max(0, int(math.floor(min(ay, by, cy))))
        hi_y = min(size - 1, int(math.ceil(max(ay, by, cy))))
        pa, pb, pc = (mesh.vertices[index] for index in vertex_ids)
        for py in range(lo_y, hi_y + 1):
            y = py + 0.5
            for px in range(lo_x, hi_x + 1):
                x = px + 0.5
                w0 = _edge(bx, by, cx, cy, x, y) / area
                w1 = _edge(cx, cy, ax, ay, x, y) / area
                w2 = 1.0 - w0 - w1
                if w0 < -1e-7 or w1 < -1e-7 or w2 < -1e-7:
                    continue
                index = py * size + px
                if positions[index] is None:
                    covered += 1
                positions[index] = (
                    pa[0] * w0 + pb[0] * w1 + pc[0] * w2,
                    pa[1] * w0 + pb[1] * w1 + pc[1] * w2,
                    pa[2] * w0 + pb[2] * w1 + pc[2] * w2,
                )
    return positions, covered


def _mix_rgb(current: tuple[int, int, int], target: tuple[int, int, int], amount: float) -> tuple[int, int, int]:
    amount = _clamp01(amount)
    return tuple(
        max(0, min(255, round(current[channel] * (1.0 - amount) + target[channel] * amount)))
        for channel in range(3)
    )  # type: ignore[return-value]


def semantic_skin_fields(
    mesh: Mesh,
    uvmap: UVMap,
    eye_landmarks: dict[str, object],
    *,
    size: int,
    seed: int,
    spec: SkinMaterialSpec,
) -> tuple[dict[str, tuple[int, bytes]], dict[str, object]]:
    if size < 16:
        raise ValueError("semantic skin texture size must be >=16")
    uv_report = validate_uv(mesh, uvmap)
    if uv_report["status"] != "pass":
        raise ValueError(f"semantic skin requires valid preserved UV state: {uv_report}")
    landmarks = derive_face_landmarks(mesh, eye_landmarks)
    sampled_positions, covered = _raster_positions(mesh, uvmap, size)
    if covered <= 0:
        raise ValueError("semantic skin UV rasterizer covered no pixels")

    fields = skin_fields(size, seed, spec)
    base = bytearray(fields["base_color"][1])
    roughness = bytearray(fields["roughness"][1])
    normal = bytearray(fields["normal"][1])
    ao = bytearray(fields["ao"][1])
    subsurface = bytearray(fields["subsurface_mask"][1])
    thickness = bytearray(fields["thickness"][1])
    region_debug = bytearray(size * size * 3)

    lo, hi = landmarks.bounds_min, landmarks.bounds_max
    x_span = max(hi[0] - lo[0], 1e-9)
    y_span = max(hi[1] - lo[1], 1e-9)
    z_span = max(hi[2] - lo[2], 1e-9)
    eye_y = (landmarks.left_eye[1] + landmarks.right_eye[1]) * 0.5
    eye_x = abs(landmarks.left_eye[0] - landmarks.right_eye[0]) * 0.5
    mouth = landmarks.mouth_center
    nose = landmarks.nose_tip

    region_max = {"lips": 0.0, "nose_tzone": 0.0, "cheeks": 0.0, "ears": 0.0, "under_eye": 0.0}
    semantic_pixels = 0
    for index, point in enumerate(sampled_positions):
        if point is None:
            continue
        x, y, z = point
        frontness = _smoothstep(lo[2] + z_span * 0.42, lo[2] + z_span * 0.78, z)
        lips = _gaussian2(x, y, mouth[0], mouth[1], x_span * 0.13, y_span * 0.045) * frontness
        nose_mask = _gaussian2(x, y, nose[0], nose[1], x_span * 0.12, y_span * 0.16) * frontness
        forehead = _gaussian2(x, y, 0.0, eye_y + y_span * 0.19, x_span * 0.16, y_span * 0.18) * frontness
        tzone = _clamp01(nose_mask + forehead * 0.55)
        cheek_y = mouth[1] * 0.43 + eye_y * 0.57
        left_cheek = _gaussian2(x, y, -max(eye_x * 0.72, x_span * 0.18), cheek_y, x_span * 0.18, y_span * 0.13) * frontness
        right_cheek = _gaussian2(x, y, max(eye_x * 0.72, x_span * 0.18), cheek_y, x_span * 0.18, y_span * 0.13) * frontness
        cheeks = max(left_cheek, right_cheek)
        lateral = _smoothstep(x_span * 0.34, x_span * 0.47, abs(x))
        ears = lateral * _gaussian2(x, y, x, eye_y - y_span * 0.02, x_span, y_span * 0.17) * (0.45 + 0.55 * (1.0 - frontness))
        left_under = _gaussian2(x, y, landmarks.left_eye[0], landmarks.left_eye[1] - y_span * 0.045, x_span * 0.095, y_span * 0.055) * frontness
        right_under = _gaussian2(x, y, landmarks.right_eye[0], landmarks.right_eye[1] - y_span * 0.045, x_span * 0.095, y_span * 0.055) * frontness
        under_eye = max(left_under, right_under)

        region_max["lips"] = max(region_max["lips"], lips)
        region_max["nose_tzone"] = max(region_max["nose_tzone"], tzone)
        region_max["cheeks"] = max(region_max["cheeks"], cheeks)
        region_max["ears"] = max(region_max["ears"], ears)
        region_max["under_eye"] = max(region_max["under_eye"], under_eye)
        if max(lips, tzone, cheeks, ears, under_eye) > 0.12:
            semantic_pixels += 1

        base_offset = index * 3
        current = (base[base_offset], base[base_offset + 1], base[base_offset + 2])
        current = _mix_rgb(current, (150, 75, 72), lips * 0.52)
        current = _mix_rgb(current, (172, 111, 98), cheeks * 0.14)
        current = _mix_rgb(current, (170, 104, 94), nose_mask * 0.12)
        current = _mix_rgb(current, (171, 103, 95), ears * 0.24)
        current = _mix_rgb(current, (139, 91, 91), under_eye * 0.10)
        base[base_offset:base_offset + 3] = bytes(current)

        rough = roughness[index] / 255.0
        rough += ears * 0.045 + cheeks * 0.018
        rough -= tzone * 0.075 + lips * 0.10
        roughness[index] = max(0, min(255, round(_clamp01(rough) * 255.0)))

        # Lips should not inherit full pore relief from generic skin noise.
        flat_amount = lips * 0.72
        normal[base_offset] = round(normal[base_offset] * (1.0 - flat_amount) + 128 * flat_amount)
        normal[base_offset + 1] = round(normal[base_offset + 1] * (1.0 - flat_amount) + 128 * flat_amount)
        normal[base_offset + 2] = round(normal[base_offset + 2] * (1.0 - flat_amount) + 255 * flat_amount)

        sss = subsurface[index] / 255.0
        sss += lips * 0.16 + ears * 0.12 + cheeks * 0.04
        subsurface[index] = max(0, min(255, round(_clamp01(sss) * 255.0)))
        thick = thickness[index] / 255.0
        thick -= ears * 0.14 + lips * 0.05
        thickness[index] = max(0, min(255, round(_clamp01(thick) * 255.0)))

        region_debug[base_offset] = max(0, min(255, round(max(lips, under_eye * 0.5) * 255.0)))
        region_debug[base_offset + 1] = max(0, min(255, round(max(cheeks, ears * 0.7) * 255.0)))
        region_debug[base_offset + 2] = max(0, min(255, round(tzone * 255.0)))

    orm = bytearray()
    for index in range(size * size):
        orm.extend((ao[index], roughness[index], 0))

    output = {
        "base_color": (3, bytes(base)),
        "roughness": (1, bytes(roughness)),
        "height": fields["height"],
        "normal": (3, bytes(normal)),
        "ao": (1, bytes(ao)),
        "subsurface_mask": (1, bytes(subsurface)),
        "thickness": (1, bytes(thickness)),
        "orm": (3, bytes(orm)),
        "region_debug": (3, bytes(region_debug)),
    }
    evidence = {
        "uv_pixels": size * size,
        "covered_pixels": covered,
        "coverage": covered / float(size * size),
        "semantic_pixels": semantic_pixels,
        "semantic_fraction_of_covered": semantic_pixels / float(max(covered, 1)),
        "region_max": region_max,
        "landmarks": {
            "mouth_center": list(landmarks.mouth_center),
            "mouth_boundary_vertices": landmarks.mouth_boundary_vertices,
            "nose_tip": list(landmarks.nose_tip),
            "left_eye": list(landmarks.left_eye),
            "right_eye": list(landmarks.right_eye),
        },
    }
    return output, evidence


def write_hm08_semantic_skin(
    output: str | Path,
    *,
    mesh: Mesh | None = None,
    uvmap: UVMap | None = None,
    size: int = 512,
    seed: int = 20801,
    spec: SkinMaterialSpec | None = None,
) -> dict[str, object]:
    root = Path(output)
    root.mkdir(parents=True, exist_ok=True)
    if mesh is None or uvmap is None:
        mesh, uvmap = read_obj_uv(SEED_ROOT / "head.obj", name="hm08_head_v0_2")
    eye_landmarks = json.loads((SEED_ROOT / "eye-landmarks.json").read_text(encoding="utf-8"))
    spec = spec or SkinMaterialSpec(
        base_rgb=(166, 119, 101),
        undertone_rgb=(142, 72, 67),
        roughness=0.52,
        oiliness=0.12,
        pore_strength=0.34,
        freckle_density=0.014,
        subsurface_weight_hint=0.56,
        specular_ior_hint=1.40,
    )
    fields, evidence = semantic_skin_fields(mesh, uvmap, eye_landmarks, size=size, seed=seed, spec=spec)
    maps: dict[str, dict[str, object]] = {}
    for name, (channels, pixels) in fields.items():
        data = png_bytes(size, size, channels, pixels)
        filename = f"{name}.png"
        (root / filename).write_bytes(data)
        maps[name] = {"file": filename, "channels": channels, "sha256": _sha(data)}
    manifest: dict[str, object] = {
        "schema": SCHEMA,
        "kind": "geometry_grounded_semantic_human_skin",
        "seed": seed,
        "size": [size, size],
        "maps": maps,
        "evidence": evidence,
        "openpbr_hints": {
            "base_metalness": 0.0,
            "specular_ior": spec.specular_ior_hint,
            "subsurface_weight": spec.subsurface_weight_hint,
            "interpretation": "Authored renderer starting points. Not measured tissue parameters."
        },
        "truth": {
            "physically_measured": False,
            "human_scan": False,
            "deterministic": True,
            "semantic_regions_source": "derived from canonical hm08 geometry plus pinned helper-eye metadata",
            "notes": [
                "Lip, T-zone, cheek, ear and under-eye modulation is geometry-grounded rather than painted from a scan.",
                "Region masks are deliberately soft authored heuristics and remain replaceable state.",
                "Subsurface/thickness maps remain renderer proxies; real skin scattering still needs engine-specific validation."
            ]
        },
    }
    payload = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8")
    (root / "semantic-skin.json").write_bytes(payload)
    manifest["manifest_sha256"] = _sha(payload)
    return manifest


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("output", nargs="?", default="build/hm08-semantic-skin")
    parser.add_argument("--size", type=int, default=128)
    parser.add_argument("--seed", type=int, default=20801)
    args = parser.parse_args()
    result = write_hm08_semantic_skin(args.output, size=args.size, seed=args.seed)
    print(json.dumps({"evidence": result["evidence"], "truth": result["truth"]}, indent=2))
