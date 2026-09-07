#!/usr/bin/env python3
"""Derive a compact, source-indexed human head seed from MakeHuman hm08.

This is a one-time/bootstrap fidelity tool. It does not depend on MakeHuman
application code. It operates on pinned CC0 data files and preserves enough
source mapping that original hm08 sparse targets can be remapped without
silently changing meaning.

Coordinate rule:
- The canonical seed remains in the raw MakeHuman base.obj coordinate system.
- MakeHuman .target delta triples are therefore copied directly.
- Blender/engine axis conversion, if needed, belongs downstream and must be
  explicit. Do not apply MPFB's Blender conversion inside this bootstrap.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict, deque
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

SCHEMA = "axm.game-assets.hm08-head-seed.v0.1"


@dataclass(slots=True)
class ObjFace:
    vertices: tuple[int, ...]
    texcoords: tuple[int | None, ...]


def _sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _git_blob_sha(path: Path) -> str:
    data = path.read_bytes()
    header = f"blob {len(data)}\0".encode("ascii")
    return hashlib.sha1(header + data).hexdigest()


def parse_obj(path: Path) -> tuple[list[tuple[float, float, float]], list[tuple[float, float]], list[ObjFace]]:
    vertices: list[tuple[float, float, float]] = []
    texcoords: list[tuple[float, float]] = []
    faces: list[ObjFace] = []
    for line_number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if parts[0] == "v" and len(parts) >= 4:
            vertices.append((float(parts[1]), float(parts[2]), float(parts[3])))
        elif parts[0] == "vt" and len(parts) >= 3:
            texcoords.append((float(parts[1]), float(parts[2])))
        elif parts[0] == "f" and len(parts) >= 4:
            face_vertices: list[int] = []
            face_uvs: list[int | None] = []
            for token in parts[1:]:
                fields = token.split("/")
                raw_v = int(fields[0])
                v = len(vertices) + raw_v if raw_v < 0 else raw_v - 1
                face_vertices.append(v)
                if len(fields) > 1 and fields[1]:
                    raw_uv = int(fields[1])
                    uv = len(texcoords) + raw_uv if raw_uv < 0 else raw_uv - 1
                    face_uvs.append(uv)
                else:
                    face_uvs.append(None)
            faces.append(ObjFace(tuple(face_vertices), tuple(face_uvs)))
    if not vertices or not faces:
        raise ValueError(f"OBJ {path} has no usable geometry")
    return vertices, texcoords, faces


def _axis_bounds(vertices: list[tuple[float, float, float]], dimensions: dict[str, int]) -> tuple[tuple[float, float], tuple[float, float], tuple[float, float]]:
    bounds = []
    for axis, axis_name in enumerate(("x", "y", "z")):
        lo_index = int(dimensions[f"{axis_name}min"])
        hi_index = int(dimensions[f"{axis_name}max"])
        if lo_index >= len(vertices) or hi_index >= len(vertices):
            raise ValueError(f"hm08 dimension index outside source mesh for {axis_name}")
        a = vertices[lo_index][axis]
        b = vertices[hi_index][axis]
        bounds.append((min(a, b), max(a, b)))
    return bounds[0], bounds[1], bounds[2]


def _inside(point: tuple[float, float, float], bounds, epsilon: float = 1e-7) -> bool:
    return all(bounds[axis][0] - epsilon <= point[axis] <= bounds[axis][1] + epsilon for axis in range(3))


def _largest_face_component(faces: list[ObjFace]) -> list[ObjFace]:
    if not faces:
        return []
    vertex_to_faces: dict[int, list[int]] = defaultdict(list)
    for face_index, face in enumerate(faces):
        for vertex in face.vertices:
            vertex_to_faces[vertex].append(face_index)
    visited: set[int] = set()
    components: list[list[int]] = []
    for start in range(len(faces)):
        if start in visited:
            continue
        queue = deque([start])
        visited.add(start)
        component = []
        while queue:
            current = queue.popleft()
            component.append(current)
            for vertex in faces[current].vertices:
                for neighbor in vertex_to_faces[vertex]:
                    if neighbor not in visited:
                        visited.add(neighbor)
                        queue.append(neighbor)
        components.append(component)
    biggest = max(components, key=len)
    return [faces[index] for index in biggest]


def derive_head(
    base_obj: Path,
    config_json: Path,
) -> tuple[list[tuple[float, float, float]], list[tuple[float, float]], list[ObjFace], dict[int, int], dict[str, object]]:
    vertices, texcoords, faces = parse_obj(base_obj)
    config = json.loads(config_json.read_text(encoding="utf-8"))
    head_dimensions = config["dimensions"]["Head"]
    body_start, body_end = (int(v) for v in config["groups_by_range"]["body"])
    bounds = _axis_bounds(vertices, head_dimensions)

    eligible = {
        index
        for index in range(body_start, min(body_end + 1, len(vertices)))
        if _inside(vertices[index], bounds)
    }
    candidate_faces = [face for face in faces if face.vertices and all(vertex in eligible for vertex in face.vertices)]
    head_faces = _largest_face_component(candidate_faces)
    if len(head_faces) < 500:
        raise ValueError(f"derived head unexpectedly small: {len(head_faces)} faces")

    used_source_vertices = sorted({vertex for face in head_faces for vertex in face.vertices})
    source_to_compact = {source: compact for compact, source in enumerate(used_source_vertices)}
    compact_vertices = [vertices[source] for source in used_source_vertices]

    used_source_uvs = sorted({uv for face in head_faces for uv in face.texcoords if uv is not None})
    uv_to_compact = {source: compact for compact, source in enumerate(used_source_uvs)}
    compact_uvs = [texcoords[source] for source in used_source_uvs]
    compact_faces = [
        ObjFace(
            tuple(source_to_compact[index] for index in face.vertices),
            tuple(uv_to_compact[uv] if uv is not None else None for uv in face.texcoords),
        )
        for face in head_faces
    ]

    report = {
        "source_vertices": len(vertices),
        "source_faces": len(faces),
        "body_range": [body_start, body_end],
        "head_bounds": {
            "x": list(bounds[0]),
            "y": list(bounds[1]),
            "z": list(bounds[2]),
            "extrema_source_indices": head_dimensions,
        },
        "eligible_body_vertices": len(eligible),
        "candidate_faces": len(candidate_faces),
        "compact_vertices": len(compact_vertices),
        "compact_faces": len(compact_faces),
        "compact_uvs": len(compact_uvs),
        "source_vertex_min": min(used_source_vertices),
        "source_vertex_max": max(used_source_vertices),
    }
    return compact_vertices, compact_uvs, compact_faces, source_to_compact, report


def write_obj(path: Path, vertices, texcoords, faces: Iterable[ObjFace]) -> None:
    lines = [
        "# AXM compact hm08 head seed",
        "# Derived from pinned MakeHuman CC0 base.obj; see seed-manifest.json",
        "o axm_hm08_head",
    ]
    for x, y, z in vertices:
        lines.append(f"v {x:.9g} {y:.9g} {z:.9g}")
    for u, v in texcoords:
        lines.append(f"vt {u:.9g} {v:.9g}")
    for face in faces:
        tokens = []
        for vertex, uv in zip(face.vertices, face.texcoords):
            tokens.append(f"{vertex + 1}/{uv + 1}" if uv is not None else str(vertex + 1))
        lines.append("f " + " ".join(tokens))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def remap_target(source_path: Path, source_to_compact: dict[int, int], output_path: Path) -> dict[str, object]:
    comments = []
    rows: list[tuple[int, float, float, float]] = []
    source_rows = 0
    for raw in source_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("#"):
            comments.append(line)
            continue
        fields = line.split()
        if len(fields) != 4:
            continue
        source_rows += 1
        source_index = int(fields[0])
        compact_index = source_to_compact.get(source_index)
        if compact_index is None:
            continue
        rows.append((compact_index, float(fields[1]), float(fields[2]), float(fields[3])))
    if not rows:
        raise ValueError(f"target {source_path.name} has no rows inside derived head")
    lines = [
        "# AXM remapped sparse target",
        "# Original target is CC0 MakeHuman hm08 data; see seed-manifest.json",
        "# basemesh axm-hm08-head-v0.1",
        f"# source_target {source_path.name}",
    ]
    for index, dx, dy, dz in sorted(rows):
        lines.append(f"{index} {dx:.9g} {dy:.9g} {dz:.9g}")
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {
        "name": output_path.name,
        "source_name": source_path.name,
        "source_rows": source_rows,
        "retained_rows": len(rows),
        "source_sha256": _sha256(source_path),
        "source_git_blob_sha1": _git_blob_sha(source_path),
        "output_sha256": _sha256(output_path),
    }


def build(args: argparse.Namespace) -> dict[str, object]:
    base = Path(args.base_obj)
    config = Path(args.config_json)
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    targets_dir = output / "targets"
    targets_dir.mkdir(exist_ok=True)

    vertices, texcoords, faces, source_to_compact, extraction = derive_head(base, config)
    head_obj = output / "head.obj"
    write_obj(head_obj, vertices, texcoords, faces)

    mapping_path = output / "source-index-map.json"
    mapping = {
        "schema": "axm.game-assets.hm08-head-source-map.v0.1",
        "source_to_compact": {str(source): compact for source, compact in sorted(source_to_compact.items())},
        "compact_to_source": [source for source, _ in sorted(source_to_compact.items(), key=lambda item: item[1])],
    }
    mapping_path.write_text(json.dumps(mapping, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    target_reports = []
    for target_path in args.target:
        source = Path(target_path)
        target_reports.append(remap_target(source, source_to_compact, targets_dir / source.name))

    manifest: dict[str, object] = {
        "schema": SCHEMA,
        "basemesh_id": "axm-hm08-head-v0.1",
        "coordinate_space": {
            "name": "raw_makehuman_hm08_obj",
            "target_delta_rule": "direct_copy_from_raw_makehuman_target",
            "engine_conversion_applied": False,
        },
        "source": {
            "makehuman_revision": args.makehuman_revision,
            "makehuman_base_obj_git_blob_sha1": _git_blob_sha(base),
            "makehuman_base_obj_sha256": _sha256(base),
            "mpfb_revision": args.mpfb_revision,
            "mpfb_hm08_config_git_blob_sha1": _git_blob_sha(config),
            "mpfb_hm08_config_sha256": _sha256(config),
            "license_record": "MakeHuman base mesh/targets: CC0 source data; this tool does not import MakeHuman application code.",
        },
        "extraction": extraction,
        "outputs": {
            "head_obj": {"file": "head.obj", "sha256": _sha256(head_obj)},
            "source_index_map": {"file": "source-index-map.json", "sha256": _sha256(mapping_path)},
            "targets": target_reports,
        },
        "acceptance": {
            "real_hm08_source_used": len(vertices) >= 500 and len(faces) >= 500,
            "source_index_map_complete": len(source_to_compact) == len(vertices),
            "source_uvs_preserved": len(texcoords) > 0,
            "targets_retained": all(int(report["retained_rows"]) > 0 for report in target_reports),
        },
        "truth": {
            "high_end_anatomy_claim": False,
            "notes": [
                "This seed replaces the procedural head-like sphere with real fixed human topology.",
                "The head is derived mechanically from hm08 Head extrema metadata and the largest connected body-face component inside those bounds.",
                "The compact neck boundary is expected to be open; closed-manifold status is not required for a head extraction.",
                "Retained source UVs and source vertex indices are preserved for later skin/eye/hair and target lineage work.",
            ],
        },
    }
    manifest_path = output / "seed-manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    manifest["manifest_sha256"] = _sha256(manifest_path)
    if not all(manifest["acceptance"].values()):
        raise ValueError(f"hm08 head seed acceptance failed: {manifest['acceptance']}")
    return manifest


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser()
    p.add_argument("--base-obj", required=True)
    p.add_argument("--config-json", required=True)
    p.add_argument("--target", action="append", default=[])
    p.add_argument("--output", required=True)
    p.add_argument("--makehuman-revision", required=True)
    p.add_argument("--mpfb-revision", required=True)
    return p


if __name__ == "__main__":
    result = build(parser().parse_args())
    print(json.dumps({"acceptance": result["acceptance"], "extraction": result["extraction"]}, indent=2))
