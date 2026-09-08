#!/usr/bin/env python3
"""Derive AXM hm08 human head seed v0.2 from pinned CC0 source data.

v0.1 used all six MPFB Head extrema as a hard 3D crop. That passed structural
checks but real visual inspection exposed artificial scalp/side cut boundaries.
v0.2 keeps the same pinned source, UV and target lineage but uses only the
metadata-derived vertical head slab, then retains the largest connected body
surface. This avoids clipping the head on scale-landmark X/depth extrema.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from bootstrap_hm08_head import (
    ObjFace,
    _git_blob_sha,
    _largest_face_component,
    _raw_makehuman_bounds_from_mpfb_dimensions,
    _sha256,
    parse_obj,
    write_obj,
)

SCHEMA = "axm.game-assets.hm08-head-seed.v0.2"
BASEMESH_ID = "axm-hm08-head-v0.2"


def derive_head_vertical(
    base_obj: Path,
    config_json: Path,
    *,
    minimum_faces: int = 500,
) -> tuple[list[tuple[float, float, float]], list[tuple[float, float]], list[ObjFace], dict[int, int], dict[str, object]]:
    vertices, texcoords, faces = parse_obj(base_obj)
    config = json.loads(config_json.read_text(encoding="utf-8"))
    dimensions = config["dimensions"]["Head"]
    body_start, body_end = (int(v) for v in config["groups_by_range"]["body"])
    metadata_bounds = _raw_makehuman_bounds_from_mpfb_dimensions(vertices, dimensions)
    y_min, y_max = metadata_bounds[1]
    epsilon = 1e-7

    eligible = {
        index
        for index in range(body_start, min(body_end + 1, len(vertices)))
        if y_min - epsilon <= vertices[index][1] <= y_max + epsilon
    }
    candidate_faces = [
        face for face in faces
        if face.vertices and all(vertex in eligible for vertex in face.vertices)
    ]
    head_faces = _largest_face_component(candidate_faces)
    if len(head_faces) < minimum_faces:
        raise ValueError(
            "v0.2 head unexpectedly small: "
            f"{len(head_faces)} faces < {minimum_faces}; "
            f"eligible_vertices={len(eligible)} candidate_faces={len(candidate_faces)} "
            f"vertical_slab={[y_min, y_max]}"
        )

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

    xs = [value[0] for value in compact_vertices]
    ys = [value[1] for value in compact_vertices]
    zs = [value[2] for value in compact_vertices]
    actual_bounds = {
        "x": [min(xs), max(xs)],
        "y": [min(ys), max(ys)],
        "z": [min(zs), max(zs)],
    }
    report = {
        "selection_method": "metadata_vertical_slab_then_largest_connected_body_surface",
        "source_vertices": len(vertices),
        "source_faces": len(faces),
        "body_range": [body_start, body_end],
        "metadata_reference_bounds": {
            "coordinate_space": "raw_makehuman_hm08_obj",
            "x": list(metadata_bounds[0]),
            "y": list(metadata_bounds[1]),
            "z": list(metadata_bounds[2]),
            "mpfb_extrema_source_indices": dimensions,
            "note": "Only raw-Y vertical bounds are used for v0.2 face selection. X/Z are retained as reference scale landmarks, not crop planes.",
        },
        "vertical_slab_y": [y_min, y_max],
        "eligible_body_vertices": len(eligible),
        "candidate_faces": len(candidate_faces),
        "compact_vertices": len(compact_vertices),
        "compact_faces": len(compact_faces),
        "compact_uvs": len(compact_uvs),
        "compact_actual_bounds": actual_bounds,
        "source_vertex_min": min(used_source_vertices),
        "source_vertex_max": max(used_source_vertices),
    }
    return compact_vertices, compact_uvs, compact_faces, source_to_compact, report


def remap_target_v2(source_path: Path, source_to_compact: dict[int, int], output_path: Path) -> dict[str, object]:
    rows: list[tuple[int, float, float, float]] = []
    source_rows = 0
    for raw in source_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
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
        raise ValueError(f"target {source_path.name} has no rows inside v0.2 head")
    lines = [
        "# AXM remapped sparse target",
        "# Original target is CC0 MakeHuman hm08 data; see seed-manifest.json",
        f"# basemesh {BASEMESH_ID}",
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

    vertices, texcoords, faces, source_to_compact, extraction = derive_head_vertical(
        base,
        config,
        minimum_faces=int(getattr(args, "minimum_faces", 500)),
    )
    head_obj = output / "head.obj"
    write_obj(head_obj, vertices, texcoords, faces)

    mapping_path = output / "source-index-map.json"
    mapping = {
        "schema": "axm.game-assets.hm08-head-source-map.v0.2",
        "source_to_compact": {str(source): compact for source, compact in sorted(source_to_compact.items())},
        "compact_to_source": [source for source, _ in sorted(source_to_compact.items(), key=lambda item: item[1])],
    }
    mapping_path.write_text(json.dumps(mapping, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    target_reports = [
        remap_target_v2(Path(target_path), source_to_compact, targets_dir / Path(target_path).name)
        for target_path in args.target
    ]
    real_threshold = int(getattr(args, "real_threshold", 500))
    manifest: dict[str, object] = {
        "schema": SCHEMA,
        "basemesh_id": BASEMESH_ID,
        "coordinate_space": {
            "name": "raw_makehuman_hm08_obj",
            "target_delta_rule": "direct_copy_from_raw_makehuman_target",
            "mpfb_dimension_axis_rule": "Blender X=raw X, Blender Y=-raw Z, Blender Z=raw Y",
            "engine_conversion_applied": False,
        },
        "source": {
            "makehuman_revision": args.makehuman_revision,
            "makehuman_base_obj_git_blob_sha1": _git_blob_sha(base),
            "makehuman_base_obj_sha256": _sha256(base),
            "mpfb_revision": args.mpfb_revision,
            "mpfb_hm08_config_git_blob_sha1": _git_blob_sha(config),
            "mpfb_hm08_config_sha256": _sha256(config),
            "license_record": "MakeHuman base mesh/targets: CC0 source data; no MakeHuman application code is imported.",
        },
        "repair_lineage": {
            "supersedes_for_fidelity": "axm-hm08-head-v0.1",
            "v0.1_status": "structurally_valid_but_visually_rejected_for_artificial_crop_boundaries",
            "repair_reason": "Real silhouette inspection exposed extra scalp/side cut loops caused by treating scale-landmark X/Z extrema as hard crop planes.",
        },
        "extraction": extraction,
        "outputs": {
            "head_obj": {"file": "head.obj", "sha256": _sha256(head_obj)},
            "source_index_map": {"file": "source-index-map.json", "sha256": _sha256(mapping_path)},
            "targets": target_reports,
        },
        "acceptance": {
            "real_hm08_source_used": len(vertices) >= real_threshold and len(faces) >= real_threshold,
            "source_index_map_complete": len(source_to_compact) == len(vertices),
            "source_uvs_preserved": len(texcoords) > 0,
            "targets_retained": all(int(report["retained_rows"]) > 0 for report in target_reports),
            "vertical_slab_method_used": extraction["selection_method"] == "metadata_vertical_slab_then_largest_connected_body_surface",
        },
        "truth": {
            "high_end_anatomy_claim": False,
            "notes": [
                "v0.2 is an evidence-driven extraction repair, not a claim that the neutral MakeHuman face itself meets the final Sentinel fidelity target.",
                "Canonical coordinates and sparse target semantics remain raw MakeHuman hm08 state.",
                "X/depth scale extrema are preserved in the manifest but no longer used as destructive crop planes.",
            ],
        },
    }
    manifest_path = output / "seed-manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    manifest["manifest_sha256"] = _sha256(manifest_path)
    if not all(manifest["acceptance"].values()):
        raise ValueError(f"hm08 v0.2 acceptance failed: {manifest['acceptance']}")
    return manifest


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser()
    p.add_argument("--base-obj", required=True)
    p.add_argument("--config-json", required=True)
    p.add_argument("--target", action="append", default=[])
    p.add_argument("--output", required=True)
    p.add_argument("--makehuman-revision", required=True)
    p.add_argument("--mpfb-revision", required=True)
    p.add_argument("--minimum-faces", type=int, default=500)
    p.add_argument("--real-threshold", type=int, default=500)
    return p


if __name__ == "__main__":
    result = build(parser().parse_args())
    print(json.dumps({"acceptance": result["acceptance"], "extraction": result["extraction"]}, indent=2))
