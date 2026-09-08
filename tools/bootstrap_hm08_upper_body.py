#!/usr/bin/env python3
"""Derive one continuous hm08 head+neck+torso seed from pinned CC0 source data.

This is the next fidelity substrate after the repaired head seed. It deliberately
selects a single raw-MakeHuman vertical slab spanning MPFB's Torso lower bound
through the Head upper bound, then retains the largest connected body surface.
The result is one continuous source topology rather than a head mesh glued onto
a separately generated neck/torso.
"""
from __future__ import annotations

import argparse
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

SCHEMA = "axm.game-assets.hm08-upper-body-seed.v0.1"
BASEMESH_ID = "axm-hm08-upper-body-v0.1"


def derive_upper_body(
    base_obj: Path,
    config_json: Path,
    *,
    minimum_faces: int = 1000,
):
    vertices, texcoords, faces = parse_obj(base_obj)
    config = json.loads(config_json.read_text(encoding="utf-8"))
    body_start, body_end = (int(v) for v in config["groups_by_range"]["body"])
    head_bounds = _raw_makehuman_bounds_from_mpfb_dimensions(vertices, config["dimensions"]["Head"])
    torso_bounds = _raw_makehuman_bounds_from_mpfb_dimensions(vertices, config["dimensions"]["Torso"])
    y_min = min(torso_bounds[1][0], torso_bounds[1][1])
    y_max = max(head_bounds[1][0], head_bounds[1][1])
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
    upper_faces = _largest_face_component(candidate_faces)
    if len(upper_faces) < minimum_faces:
        raise ValueError(
            "upper body unexpectedly small: "
            f"{len(upper_faces)} faces < {minimum_faces}; "
            f"eligible_vertices={len(eligible)} candidate_faces={len(candidate_faces)} "
            f"vertical_slab={[y_min, y_max]}"
        )

    used_source_vertices = sorted({vertex for face in upper_faces for vertex in face.vertices})
    source_to_compact = {source: compact for compact, source in enumerate(used_source_vertices)}
    compact_vertices = [vertices[source] for source in used_source_vertices]

    used_source_uvs = sorted({uv for face in upper_faces for uv in face.texcoords if uv is not None})
    uv_to_compact = {source: compact for compact, source in enumerate(used_source_uvs)}
    compact_uvs = [texcoords[source] for source in used_source_uvs]
    compact_faces = [
        ObjFace(
            tuple(source_to_compact[index] for index in face.vertices),
            tuple(uv_to_compact[uv] if uv is not None else None for uv in face.texcoords),
        )
        for face in upper_faces
    ]

    xs = [v[0] for v in compact_vertices]
    ys = [v[1] for v in compact_vertices]
    zs = [v[2] for v in compact_vertices]
    report = {
        "selection_method": "torso_to_head_vertical_slab_then_largest_connected_body_surface",
        "source_vertices": len(vertices),
        "source_faces": len(faces),
        "body_range": [body_start, body_end],
        "head_reference_bounds": {"x": list(head_bounds[0]), "y": list(head_bounds[1]), "z": list(head_bounds[2])},
        "torso_reference_bounds": {"x": list(torso_bounds[0]), "y": list(torso_bounds[1]), "z": list(torso_bounds[2])},
        "vertical_slab_y": [y_min, y_max],
        "eligible_body_vertices": len(eligible),
        "candidate_faces": len(candidate_faces),
        "compact_vertices": len(compact_vertices),
        "compact_faces": len(compact_faces),
        "compact_uvs": len(compact_uvs),
        "compact_actual_bounds": {"x": [min(xs), max(xs)], "y": [min(ys), max(ys)], "z": [min(zs), max(zs)]},
        "source_vertex_min": min(used_source_vertices),
        "source_vertex_max": max(used_source_vertices),
    }
    return compact_vertices, compact_uvs, compact_faces, source_to_compact, report


def remap_target(source_path: Path, source_to_compact: dict[int, int], output_path: Path) -> dict[str, object]:
    rows = []
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
        if compact_index is not None:
            rows.append((compact_index, float(fields[1]), float(fields[2]), float(fields[3])))
    if not rows:
        raise ValueError(f"target {source_path.name} has no rows inside upper body")
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

    vertices, texcoords, faces, source_to_compact, extraction = derive_upper_body(
        base,
        config,
        minimum_faces=int(getattr(args, "minimum_faces", 1000)),
    )
    upper_obj = output / "upper_body.obj"
    write_obj(upper_obj, vertices, texcoords, faces)

    mapping_path = output / "source-index-map.json"
    compact_to_source = [source for source, _ in sorted(source_to_compact.items(), key=lambda item: item[1])]
    mapping = {
        "schema": "axm.game-assets.hm08-upper-body-source-map.v0.1",
        "source_to_compact": {str(source): compact for source, compact in sorted(source_to_compact.items())},
        "compact_to_source": compact_to_source,
    }
    mapping_path.write_text(json.dumps(mapping, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    target_reports = [
        remap_target(Path(target_path), source_to_compact, targets_dir / Path(target_path).name)
        for target_path in args.target
    ]

    required_head_sources: set[int] = set()
    if getattr(args, "required_head_source_map", None):
        head_map = json.loads(Path(args.required_head_source_map).read_text(encoding="utf-8"))
        required_head_sources = {int(v) for v in head_map["compact_to_source"]}
    upper_sources = set(source_to_compact)
    missing_head_sources = sorted(required_head_sources - upper_sources)

    real_threshold = int(getattr(args, "real_threshold", 1000))
    manifest: dict[str, object] = {
        "schema": SCHEMA,
        "basemesh_id": BASEMESH_ID,
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
            "license_record": "MakeHuman hm08 base mesh/targets: CC0 source data; no MakeHuman application code is imported.",
        },
        "relationship_to_head_seed": {
            "required_head_source_vertices": len(required_head_sources),
            "missing_head_source_vertices": missing_head_sources,
            "head_source_subset": not missing_head_sources,
            "purpose": "One continuous upper-body topology should contain the already-promoted repaired head source vertices rather than attaching a separate neck mesh.",
        },
        "extraction": extraction,
        "outputs": {
            "upper_body_obj": {"file": "upper_body.obj", "sha256": _sha256(upper_obj)},
            "source_index_map": {"file": "source-index-map.json", "sha256": _sha256(mapping_path)},
            "targets": target_reports,
        },
        "acceptance": {
            "real_hm08_source_used": len(vertices) >= real_threshold and len(faces) >= real_threshold,
            "source_index_map_complete": len(source_to_compact) == len(vertices),
            "source_uvs_preserved": len(texcoords) > 0,
            "targets_retained": all(int(report["retained_rows"]) > 0 for report in target_reports),
            "continuous_vertical_surface_method": extraction["selection_method"] == "torso_to_head_vertical_slab_then_largest_connected_body_surface",
            "promoted_head_source_is_subset": not missing_head_sources,
        },
        "truth": {
            "production_body_claim": False,
            "notes": [
                "This is a continuous CC0 human source substrate, not final Sentinel anatomy, musculature, rigging, or armor fit.",
                "The lower torso and arm cuts are intentional extraction boundaries for this upper-body proving stage.",
                "Facial identity targets remain sparse source layers and can be applied on this larger topology using the remapped files."
            ],
        },
    }
    manifest_path = output / "seed-manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    manifest["manifest_sha256"] = _sha256(manifest_path)
    if not all(manifest["acceptance"].values()):
        raise ValueError(f"hm08 upper-body acceptance failed: {manifest['acceptance']}")
    return manifest


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser()
    p.add_argument("--base-obj", required=True)
    p.add_argument("--config-json", required=True)
    p.add_argument("--target", action="append", default=[])
    p.add_argument("--required-head-source-map")
    p.add_argument("--output", required=True)
    p.add_argument("--makehuman-revision", required=True)
    p.add_argument("--mpfb-revision", required=True)
    p.add_argument("--minimum-faces", type=int, default=1000)
    p.add_argument("--real-threshold", type=int, default=1000)
    return p


if __name__ == "__main__":
    result = build(parser().parse_args())
    print(json.dumps({"acceptance": result["acceptance"], "extraction": result["extraction"], "relationship_to_head_seed": result["relationship_to_head_seed"]}, indent=2))
