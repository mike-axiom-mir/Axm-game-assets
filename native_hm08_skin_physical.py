#!/usr/bin/env python3
"""Physical-scale procedural skin bake for the repaired hm08 human head.

Unlike the earlier generic UV-space skin proof, this organ evaluates authored
skin variation in canonical 3D face space and then rasterizes those signals into
the preserved hm08 UV atlas. The purpose is scale stability: a pore or mottling
frequency should not become centimeter-sized merely because the head occupies a
small part of a larger UV layout.

This remains authored CG skin. It is not a scan and it does not claim measured
human tissue parameters.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

from native_geometry import Mesh
from native_hm08_landmarks import derive_hm08_face_landmarks
from native_hm08_skin_bake import _raster_positions
from native_pbr import fbm, png_bytes
from native_skin_material import SkinMaterialSpec
from native_uv import UVMap, read_obj_uv, validate_uv

SEED_ROOT = Path("seed_data/hm08_head_v0.2")
SCHEMA = "axm.game-assets.hm08-physical-skin.v0.1"


def _sha(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def _u8(value: float) -> int:
    return max(0, min(255, int(round(_clamp01(value) * 255.0))))


def _noise3(x: float, y: float, z: float, scale: float, seed: int, *, octaves: int = 4) -> float:
    """Projection-blended deterministic 3D-ish noise from the native 2D fbm organ."""
    a = fbm(x * scale, y * scale, seed + 101, octaves=octaves)
    b = fbm(y * scale, z * scale, seed + 307, octaves=octaves)
    c = fbm(z * scale, x * scale, seed + 613, octaves=octaves)
    return (a + b + c) / 3.0


def _gaussian2(x: float, y: float, cx: float, cy: float, sx: float, sy: float) -> float:
    sx = max(abs(sx), 1e-9)
    sy = max(abs(sy), 1e-9)
    dx = (x - cx) / sx
    dy = (y - cy) / sy
    return math.exp(-0.5 * (dx * dx + dy * dy))


def _smoothstep(edge0: float, edge1: float, value: float) -> float:
    if abs(edge1 - edge0) <= 1e-12:
        return 0.0
    t = _clamp01((value - edge0) / (edge1 - edge0))
    return t * t * (3.0 - 2.0 * t)


def _mix(current: tuple[float, float, float], target: tuple[float, float, float], amount: float):
    amount = _clamp01(amount)
    return tuple(current[i] * (1.0 - amount) + target[i] * amount for i in range(3))


def physical_skin_fields(
    mesh: Mesh,
    uvmap: UVMap,
    *,
    size: int,
    seed: int,
    spec: SkinMaterialSpec,
) -> tuple[dict[str, tuple[int, bytes]], dict[str, object]]:
    if size < 32:
        raise ValueError("physical skin texture size must be >=32")
    uv_report = validate_uv(mesh, uvmap)
    if uv_report["status"] != "pass":
        raise ValueError(f"physical skin requires valid hm08 UV state: {uv_report}")
    positions, covered = _raster_positions(mesh, uvmap, size)
    if covered <= 0:
        raise ValueError("physical skin UV rasterizer covered no pixels")

    eye_metadata = json.loads((SEED_ROOT / "eye-landmarks.json").read_text(encoding="utf-8"))
    landmarks = derive_hm08_face_landmarks(mesh, eye_metadata)
    lo, hi = landmarks.bounds_min, landmarks.bounds_max
    x_span = max(hi[0] - lo[0], 1e-9)
    y_span = max(hi[1] - lo[1], 1e-9)
    z_span = max(hi[2] - lo[2], 1e-9)
    eye_y = (landmarks.left_eye[1] + landmarks.right_eye[1]) * 0.5
    eye_half_sep = abs(landmarks.left_eye[0] - landmarks.right_eye[0]) * 0.5
    mouth = landmarks.mouth_center
    nose = landmarks.nose_tip

    # Background pixels use safe neutral material values. They should never be
    # sampled by valid UV triangles, but neutral padding keeps mip bleed benign.
    br, bg, bb = (float(value) for value in spec.base_rgb)
    base = bytearray([0] * size * size * 3)
    roughness = bytearray([_u8(spec.roughness)] * size * size)
    height = [0.5] * (size * size)
    ao = bytearray([255] * size * size)
    subsurface = bytearray([_u8(spec.subsurface_weight_hint)] * size * size)
    thickness = bytearray([_u8(0.56)] * size * size)
    mask = [point is not None for point in positions]

    region_max = {"lips": 0.0, "tzone": 0.0, "cheeks": 0.0, "ears": 0.0, "under_eye": 0.0}
    for index, point in enumerate(positions):
        base_offset = index * 3
        if point is None:
            base[base_offset:base_offset + 3] = bytes((int(br), int(bg), int(bb)))
            continue
        x, y, z = point
        frontness = _smoothstep(lo[2] + z_span * 0.40, lo[2] + z_span * 0.76, z)

        # Frequencies are expressed in raw hm08 decimeter space. Rough scales:
        # macro 20-50 mm, fine mottling 3-8 mm, pore relief ~0.5-1.5 mm.
        macro = _noise3(x, y, z, 2.6, seed + 1001, octaves=4)
        mottling = _noise3(x, y, z, 13.0, seed + 2003, octaves=4)
        pore = _noise3(x, y, z, 72.0, seed + 3001, octaves=3)
        fine = _noise3(x, y, z, 145.0, seed + 4001, octaves=2)

        lips = _gaussian2(x, y, mouth[0], mouth[1], x_span * 0.12, max((nose[1] - mouth[1]) * 0.18, y_span * 0.022)) * frontness
        nose_region = _gaussian2(x, y, nose[0], nose[1], x_span * 0.10, y_span * 0.14) * frontness
        forehead = _gaussian2(x, y, 0.0, eye_y + y_span * 0.18, x_span * 0.15, y_span * 0.18) * frontness
        tzone = _clamp01(nose_region + forehead * 0.52)
        cheek_y = mouth[1] + (eye_y - mouth[1]) * 0.58
        cheek_x = max(eye_half_sep * 0.78, x_span * 0.18)
        cheeks = max(
            _gaussian2(x, y, -cheek_x, cheek_y, x_span * 0.17, y_span * 0.13),
            _gaussian2(x, y, cheek_x, cheek_y, x_span * 0.17, y_span * 0.13),
        ) * frontness
        lateral = _smoothstep(x_span * 0.34, x_span * 0.48, abs(x))
        ears = lateral * _gaussian2(x, y, x, eye_y - y_span * 0.02, x_span, y_span * 0.16) * (0.45 + 0.55 * (1.0 - frontness))
        under_eye = max(
            _gaussian2(x, y, landmarks.left_eye[0], landmarks.left_eye[1] - y_span * 0.04, x_span * 0.085, y_span * 0.05),
            _gaussian2(x, y, landmarks.right_eye[0], landmarks.right_eye[1] - y_span * 0.04, x_span * 0.085, y_span * 0.05),
        ) * frontness
        for key, value in (("lips", lips), ("tzone", tzone), ("cheeks", cheeks), ("ears", ears), ("under_eye", under_eye)):
            region_max[key] = max(region_max[key], value)

        # Base color variation is intentionally restrained. Physical-scale
        # detail belongs primarily in roughness/normal response rather than
        # painting large random color clouds onto the face.
        shade = 0.965 + (macro - 0.5) * 0.055 + (mottling - 0.5) * 0.025
        color = (br * shade, bg * shade, bb * shade)
        color = _mix(color, (151.0, 82.0, 76.0), lips * 0.48)
        color = _mix(color, (176.0, 109.0, 98.0), cheeks * 0.10)
        color = _mix(color, (172.0, 104.0, 96.0), ears * 0.17)
        color = _mix(color, (146.0, 96.0, 96.0), under_eye * 0.07)
        base[base_offset:base_offset + 3] = bytes(max(0, min(255, round(value))) for value in color)

        rough = spec.roughness + (pore - 0.5) * 0.025 + (fine - 0.5) * 0.018
        rough += cheeks * 0.012 + ears * 0.025
        rough -= tzone * 0.050 + lips * 0.085
        roughness[index] = _u8(rough)

        # Height amplitude is deliberately tiny. The earlier UV-space proof
        # exaggerated surface response; this layer targets sub-millimeter feel.
        micro = (pore - 0.5) * 0.018 * spec.pore_strength + (fine - 0.5) * 0.006 * spec.pore_strength
        height[index] = _clamp01(0.5 + micro * (1.0 - lips * 0.78))
        ao[index] = _u8(0.985 + (pore - 0.5) * 0.010)
        subsurface[index] = _u8(spec.subsurface_weight_hint + lips * 0.12 + ears * 0.08 + cheeks * 0.025)
        thickness[index] = _u8(0.57 - ears * 0.12 - lips * 0.04 + (macro - 0.5) * 0.04)

    # Normal derivation only uses UV-neighbor derivatives when both neighbors
    # are covered by the same rasterized atlas. Island edges stay flat to avoid
    # inventing huge seam normals from unrelated pixels.
    normal = bytearray(size * size * 3)
    for y in range(size):
        for x in range(size):
            index = y * size + x
            base_offset = index * 3
            if not mask[index]:
                normal[base_offset:base_offset + 3] = bytes((128, 128, 255))
                continue
            xl = max(0, x - 1); xr = min(size - 1, x + 1)
            yd = max(0, y - 1); yu = min(size - 1, y + 1)
            neighbors = [y * size + xl, y * size + xr, yd * size + x, yu * size + x]
            if not all(mask[n] for n in neighbors):
                normal[base_offset:base_offset + 3] = bytes((128, 128, 255))
                continue
            left, right, down, up = (height[n] for n in neighbors)
            dx = (right - left) * 1.35
            dy = (up - down) * 1.35
            nx, ny, nz = -dx, -dy, 1.0
            inv = 1.0 / math.sqrt(nx * nx + ny * ny + nz * nz)
            normal[base_offset:base_offset + 3] = bytes((_u8(nx * inv * 0.5 + 0.5), _u8(ny * inv * 0.5 + 0.5), _u8(nz * inv * 0.5 + 0.5)))

    orm = bytearray()
    height_bytes = bytearray(_u8(value) for value in height)
    for index in range(size * size):
        orm.extend((ao[index], roughness[index], 0))

    fields = {
        "base_color": (3, bytes(base)),
        "roughness": (1, bytes(roughness)),
        "height": (1, bytes(height_bytes)),
        "normal": (3, bytes(normal)),
        "ao": (1, bytes(ao)),
        "subsurface_mask": (1, bytes(subsurface)),
        "thickness": (1, bytes(thickness)),
        "orm": (3, bytes(orm)),
    }
    evidence = {
        "uv_pixels": size * size,
        "covered_pixels": covered,
        "coverage": covered / float(size * size),
        "noise_space": "canonical_raw_hm08_decimeters",
        "physical_scale_intent": {
            "macro": "20-50mm authored variation",
            "mottling": "3-8mm authored variation",
            "pore": "0.5-1.5mm authored response",
        },
        "region_max": region_max,
        "landmarks": {
            "nose_tip": list(landmarks.nose_tip),
            "mouth_center": list(landmarks.mouth_center),
            "chin_center": list(landmarks.chin_center),
            "left_eye": list(landmarks.left_eye),
            "right_eye": list(landmarks.right_eye),
        },
    }
    return fields, evidence


def write_hm08_physical_skin(
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
    spec = spec or SkinMaterialSpec(
        base_rgb=(166, 119, 101),
        undertone_rgb=(142, 72, 67),
        roughness=0.52,
        oiliness=0.10,
        pore_strength=0.30,
        freckle_density=0.0,
        subsurface_weight_hint=0.56,
        specular_ior_hint=1.40,
    )
    fields, evidence = physical_skin_fields(mesh, uvmap, size=size, seed=seed, spec=spec)
    maps = {}
    for name, (channels, pixels) in fields.items():
        data = png_bytes(size, size, channels, pixels)
        filename = f"{name}.png"
        (root / filename).write_bytes(data)
        maps[name] = {"file": filename, "channels": channels, "sha256": _sha(data)}
    manifest: dict[str, object] = {
        "schema": SCHEMA,
        "kind": "physical_scale_geometry_grounded_human_skin",
        "seed": seed,
        "size": [size, size],
        "maps": maps,
        "evidence": evidence,
        "openpbr_hints": {
            "base_metalness": 0.0,
            "specular_ior": spec.specular_ior_hint,
            "subsurface_weight": spec.subsurface_weight_hint,
            "interpretation": "Authored renderer starting points; not measured tissue parameters."
        },
        "truth": {
            "physically_measured": False,
            "human_scan": False,
            "deterministic": True,
            "noise_coordinate_space": "canonical 3D hm08 state, then rasterized to preserved UV",
            "notes": [
                "The main improvement over earlier skin proofs is scale stability: authored microdetail is evaluated in face space instead of atlas UV space.",
                "Region color/roughness modulation uses AXM-native facial landmarks and remains replaceable authored state.",
                "Real subsurface scattering, peach fuzz and expression wrinkles remain later engine/material gates."
            ]
        }
    }
    payload = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8")
    (root / "physical-skin.json").write_bytes(payload)
    manifest["manifest_sha256"] = _sha(payload)
    return manifest


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("output", nargs="?", default="build/hm08-physical-skin")
    parser.add_argument("--size", type=int, default=128)
    parser.add_argument("--seed", type=int, default=20801)
    args = parser.parse_args()
    result = write_hm08_physical_skin(args.output, size=args.size, seed=args.seed)
    print(json.dumps({"evidence": result["evidence"], "truth": result["truth"]}, indent=2))
