#!/usr/bin/env python3
"""Native salvage construction surfaces for AXM Game Asset Forge.

Adapted from the finished Universal Creation v0.24 salvage construction donor:
`tools/blender/axm_salvage_construction.py` at commit
`a5cc708457b7e8f33e794fdac648ae65d15a0fb4`.

The useful mechanisms are internalized as Forge-native Mesh + UVMap state:

- actual-profile corrugated sheet geometry with deterministic bounded dents;
- pinned-corner cloth/tarp geometry with sag, flutter and corner folds;
- explicit shell thickness rather than screenshot-only surface suggestion.

Universal Creation's donor is Blender Z-up. This Forge port is Y-up and imports
no Blender, NumPy, Pillow, Universal Creation runtime, model, network or cloud.
"""
from __future__ import annotations

import hashlib
import json
import math
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

from native_geometry import Mesh, Vec3, bounds, topology_report
from native_uv import UVMap, validate_uv, write_obj_uv

SCHEMA = "axm.game-assets.native-salvage-construction/v0.1"
DONOR = {
    "repo": "mike-axiom-mir/axm-universal-creation",
    "commit": "a5cc708457b7e8f33e794fdac648ae65d15a0fb4",
    "mechanism": "tools/blender/axm_salvage_construction.py",
}
EPS = 1e-12


@dataclass(slots=True)
class ConstructionPiece:
    mesh: Mesh
    uvmap: UVMap
    receipt: dict[str, Any]


class SalvageConstructionError(ValueError):
    pass


def _sha256(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _add(a: Vec3, b: Vec3) -> Vec3:
    return a[0] + b[0], a[1] + b[1], a[2] + b[2]


def _sub(a: Vec3, b: Vec3) -> Vec3:
    return a[0] - b[0], a[1] - b[1], a[2] - b[2]


def _mul(v: Vec3, scalar: float) -> Vec3:
    return v[0] * scalar, v[1] * scalar, v[2] * scalar


def _cross(a: Vec3, b: Vec3) -> Vec3:
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def _length(v: Vec3) -> float:
    return math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2])


def _normalize(v: Vec3) -> Vec3:
    length = _length(v)
    if length <= EPS:
        raise SalvageConstructionError("construction surface has a degenerate rest-plane normal")
    return v[0] / length, v[1] / length, v[2] / length


def _lerp(a: Vec3, b: Vec3, t: float) -> Vec3:
    return (
        a[0] + (b[0] - a[0]) * t,
        a[1] + (b[1] - a[1]) * t,
        a[2] + (b[2] - a[2]) * t,
    )


def _finite_vec3(value: Sequence[float], label: str) -> Vec3:
    if len(value) != 3:
        raise SalvageConstructionError(f"{label} must contain three coordinates")
    result = tuple(float(item) for item in value)
    if not all(math.isfinite(item) for item in result):
        raise SalvageConstructionError(f"{label} coordinates must be finite")
    return result  # type: ignore[return-value]


def _append_face_uv(
    uv_values: list[tuple[float, float]],
    face_uvs: list[tuple[int, ...]],
    values: Sequence[tuple[float, float]],
) -> None:
    refs = []
    for uv in values:
        refs.append(len(uv_values))
        uv_values.append((float(uv[0]), float(uv[1])))
    face_uvs.append(tuple(refs))


def _grid_shell(
    name: str,
    points: list[Vec3],
    grid_uvs: list[tuple[float, float]],
    nx: int,
    ny: int,
    *,
    thickness: float,
    normal: Vec3,
) -> tuple[Mesh, UVMap]:
    if nx < 1 or ny < 1:
        raise SalvageConstructionError("grid shell needs at least one cell per axis")
    expected = (nx + 1) * (ny + 1)
    if len(points) != expected or len(grid_uvs) != expected:
        raise SalvageConstructionError("grid point/UV count does not match subdivisions")
    if not math.isfinite(thickness) or thickness <= 0.0:
        raise SalvageConstructionError("thickness must be finite and positive")

    half = thickness * 0.5
    offset = _mul(_normalize(normal), half)
    front = [_add(point, offset) for point in points]
    back = [_sub(point, offset) for point in points]
    vertices = front + back
    layer = len(front)
    faces: list[tuple[int, ...]] = []
    uv_values: list[tuple[float, float]] = []
    face_uvs: list[tuple[int, ...]] = []

    def index(x: int, y: int) -> int:
        return y * (nx + 1) + x

    for y in range(ny):
        for x in range(nx):
            a = index(x, y)
            b = index(x + 1, y)
            c = index(x + 1, y + 1)
            d = index(x, y + 1)
            faces.append((a, b, c, d))
            _append_face_uv(uv_values, face_uvs, (grid_uvs[a], grid_uvs[b], grid_uvs[c], grid_uvs[d]))
            faces.append((d + layer, c + layer, b + layer, a + layer))
            _append_face_uv(uv_values, face_uvs, (grid_uvs[d], grid_uvs[c], grid_uvs[b], grid_uvs[a]))

    # Close all four perimeter bands. The side UVs are intentionally local; the
    # broad authored surface mapping lives on the front/back grids.
    perimeter: list[tuple[int, int]] = []
    for x in range(nx):
        perimeter.append((index(x, 0), index(x + 1, 0)))
    for y in range(ny):
        perimeter.append((index(nx, y), index(nx, y + 1)))
    for x in range(nx, 0, -1):
        perimeter.append((index(x, ny), index(x - 1, ny)))
    for y in range(ny, 0, -1):
        perimeter.append((index(0, y), index(0, y - 1)))
    perimeter_count = max(1, len(perimeter))
    for edge_index, (a, b) in enumerate(perimeter):
        faces.append((a, a + layer, b + layer, b))
        u0 = edge_index / perimeter_count
        u1 = (edge_index + 1) / perimeter_count
        _append_face_uv(uv_values, face_uvs, ((u0, 0.0), (u0, 1.0), (u1, 1.0), (u1, 0.0)))

    mesh = Mesh(name, vertices, faces)
    uvmap = UVMap(uv_values, face_uvs, "native_salvage_grid_shell")
    uv_report = validate_uv(mesh, uvmap)
    if uv_report["status"] != "pass":
        raise SalvageConstructionError(f"generated UV state is invalid: {uv_report}")
    topology = topology_report(mesh)
    if topology["invalid_indices"] or topology["degenerate_faces"]:
        raise SalvageConstructionError(f"generated shell topology is invalid: {topology}")
    return mesh, uvmap


def _base_receipt(kind: str, name: str, mesh: Mesh, uvmap: UVMap, spec: dict[str, Any]) -> dict[str, Any]:
    lo, hi = bounds(mesh)
    receipt: dict[str, Any] = {
        "schema": SCHEMA,
        "kind": kind,
        "name": name,
        "coordinate_system": "Y-up",
        "spec": spec,
        "bounds": {"min": list(lo), "max": list(hi)},
        "topology": topology_report(mesh),
        "uv": validate_uv(mesh, uvmap),
        "provenance": {
            "donor": DONOR,
            "implementation": "AXM Game Asset Forge native Y-up adaptation",
        },
        "truth_boundary": {
            "geometry_generated": True,
            "explicit_thickness": True,
            "physics_simulation": False,
            "aesthetic_approval": False,
            "automatic_genome_mutation": False,
            "automatic_canon": False,
        },
    }
    receipt["receipt_digest"] = _sha256(_canonical(receipt))
    return receipt


def corrugated_sheet(
    *,
    name: str = "corrugated-sheet",
    center: Vec3 = (0.0, 0.0, 0.0),
    width: float = 1.0,
    height: float = 1.0,
    thickness: float = 0.014,
    seed: int = 1,
    corrugations_per_unit: float = 6.0,
    ridge_amplitude: float = 0.026,
    dent_amplitude: float = 0.035,
    subdivisions_y: int = 8,
    subdivisions_x: int | None = None,
    uv_tiles: tuple[float, float] = (0.8, 0.8),
) -> ConstructionPiece:
    if width <= 0.0 or height <= 0.0:
        raise SalvageConstructionError("width and height must be positive")
    for label, value in (
        ("corrugations_per_unit", corrugations_per_unit),
        ("ridge_amplitude", ridge_amplitude),
        ("dent_amplitude", dent_amplitude),
    ):
        if not math.isfinite(value) or value < 0.0:
            raise SalvageConstructionError(f"{label} must be finite and non-negative")
    nx = subdivisions_x if subdivisions_x is not None else max(18, int(width * 72))
    ny = int(subdivisions_y)
    if nx < 2 or ny < 2:
        raise SalvageConstructionError("corrugated sheet subdivisions must be >= 2")
    cx, cy, cz = _finite_vec3(center, "center")
    rng = random.Random(seed)
    phase = rng.random() * math.tau
    points: list[Vec3] = []
    uvs: list[tuple[float, float]] = []
    for j in range(ny + 1):
        v = j / ny
        for i in range(nx + 1):
            u = i / nx
            x = cx + (u - 0.5) * width
            y = cy + (v - 0.5) * height
            ridge = ridge_amplitude * math.cos(u * width * math.tau * corrugations_per_unit)
            dent = dent_amplitude * math.sin(u * 13.0 + phase) * math.sin(v * 5.0) * math.sin(math.pi * u)
            z = cz + ridge + dent
            points.append((x, y, z))
            uvs.append((u * width * uv_tiles[0], v * height * uv_tiles[1]))
    mesh, uvmap = _grid_shell(
        name,
        points,
        uvs,
        nx,
        ny,
        thickness=thickness,
        normal=(0.0, 0.0, 1.0),
    )
    receipt = _base_receipt(
        "corrugated_sheet",
        name,
        mesh,
        uvmap,
        {
            "center": [cx, cy, cz],
            "width": width,
            "height": height,
            "thickness": thickness,
            "seed": seed,
            "corrugations_per_unit": corrugations_per_unit,
            "ridge_amplitude": ridge_amplitude,
            "dent_amplitude": dent_amplitude,
            "subdivisions": [nx, ny],
            "uv_tiles": list(uv_tiles),
        },
    )
    return ConstructionPiece(mesh, uvmap, receipt)


def cloth_patch(
    corners: Sequence[Sequence[float]],
    *,
    name: str = "cloth-patch",
    sag: float = 0.22,
    subdivisions: tuple[int, int] = (32, 24),
    flutter: float = 0.022,
    edge_sag: float = 0.0,
    corner_folds: float = 0.0,
    thickness: float = 0.008,
    uv_tiles: tuple[float, float] = (1.0, 1.0),
) -> ConstructionPiece:
    if len(corners) != 4:
        raise SalvageConstructionError("cloth patch requires four pinned corners")
    a, b, c, d = tuple(_finite_vec3(value, f"corner[{index}]") for index, value in enumerate(corners))
    nx, ny = int(subdivisions[0]), int(subdivisions[1])
    if nx < 2 or ny < 2:
        raise SalvageConstructionError("cloth subdivisions must be >= 2")
    for label, value in (
        ("sag", sag),
        ("flutter", flutter),
        ("edge_sag", edge_sag),
        ("corner_folds", corner_folds),
    ):
        if not math.isfinite(value) or value < 0.0:
            raise SalvageConstructionError(f"{label} must be finite and non-negative")

    rest_normal = _normalize(_cross(_sub(b, a), _sub(c, a)))

    def point(u: float, v: float) -> Vec3:
        top = _lerp(a, b, u)
        bottom = _lerp(c, d, u)
        p = _lerp(top, bottom, v)
        vertical = (
            sag * math.sin(math.pi * u) * math.sin(math.pi * v)
            + edge_sag * math.sin(math.pi * u) * v**3
        )
        y = p[1] - vertical
        y += flutter * math.sin(u * math.pi * 12.0 + v * 3.0) * math.sin(math.pi * u) * (0.3 + 0.7 * v)
        y += corner_folds * math.sin(math.pi * v) * (
            math.sin(v * 19.0 + u * 8.0) * math.exp(-u * 5.0)
            + 0.7 * math.sin(v * 23.0 - u * 8.0) * math.exp(-(1.0 - u) * 5.0)
        )
        z = p[2] + flutter * 0.65 * math.sin(u * 9.0 + v * 15.0) * math.sin(math.pi * v)
        return p[0], y, z

    points = [point(i / nx, j / ny) for j in range(ny + 1) for i in range(nx + 1)]
    uvs = [
        (i / nx * uv_tiles[0], (1.0 - j / ny) * uv_tiles[1])
        for j in range(ny + 1)
        for i in range(nx + 1)
    ]
    mesh, uvmap = _grid_shell(
        name,
        points,
        uvs,
        nx,
        ny,
        thickness=thickness,
        normal=rest_normal,
    )
    rest_center = _lerp(_lerp(a, b, 0.5), _lerp(c, d, 0.5), 0.5)
    deformed_center = point(0.5, 0.5)
    receipt = _base_receipt(
        "cloth_patch",
        name,
        mesh,
        uvmap,
        {
            "pinned_corners": [list(a), list(b), list(c), list(d)],
            "sag": sag,
            "subdivisions": [nx, ny],
            "flutter": flutter,
            "edge_sag": edge_sag,
            "corner_folds": corner_folds,
            "thickness": thickness,
            "uv_tiles": list(uv_tiles),
            "rest_plane_normal": list(rest_normal),
            "rest_center": list(rest_center),
            "deformed_center": list(deformed_center),
            "center_vertical_displacement": deformed_center[1] - rest_center[1],
        },
    )
    receipt["truth_boundary"]["cloth_solver"] = False
    receipt["truth_boundary"]["rest_plane_thickness_approximation"] = True
    receipt["receipt_digest"] = _sha256(_canonical({k: v for k, v in receipt.items() if k != "receipt_digest"}))
    return ConstructionPiece(mesh, uvmap, receipt)


def write_piece(
    piece: ConstructionPiece,
    obj_path: str | Path,
    receipt_path: str | Path,
) -> None:
    obj = Path(obj_path)
    receipt = Path(receipt_path)
    if obj.exists() or receipt.exists():
        raise SalvageConstructionError("construction outputs are create-only")
    obj.parent.mkdir(parents=True, exist_ok=True)
    receipt.parent.mkdir(parents=True, exist_ok=True)
    write_obj_uv(piece.mesh, piece.uvmap, obj)
    receipt.write_text(
        json.dumps(piece.receipt, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
