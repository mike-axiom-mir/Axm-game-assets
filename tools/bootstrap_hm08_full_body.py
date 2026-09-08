#!/usr/bin/env python3
"""Derive the complete continuous hm08 human body from pinned CC0 source data.

Only the canonical MakeHuman `body` vertex range is admitted. Helper eyes,
hair, lashes, teeth, tongue, clothes and genital helper geometry are not folded
into this seed. The largest connected body surface is retained, source UVs and
source indices are preserved, and the already-promoted head/upper-body source
vertices must remain exact subsets.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from bootstrap_hm08_head import (
    ObjFace,
    _git_blob_sha,
    _largest_face_component,
    _sha256,
    parse_obj,
    write_obj,
)

SCHEMA = "axm.game-assets.hm08-full-body-seed.v0.1"
BASEMESH_ID = "axm-hm08-full-body-v0.1"


def derive_full_body(base_obj: Path, config_json: Path, *, minimum_faces: int = 5000):
    vertices, texcoords, faces = parse_obj(base_obj)
    config = json.loads(config_json.read_text(encoding="utf-8"))
    body_start, body_end = (int(v) for v in config["groups_by_range"]["body"])
    body_end = min(body_end, len(vertices) - 1)
    eligible = set(range(body_start, body_end + 1))
    candidate_faces = [
        face for face in faces
        if face.vertices and all(vertex in eligible for vertex in face.vertices)
    ]
    body_faces = _largest_face_component(candidate_faces)
    if len(body_faces) < minimum_faces:
        raise ValueError(
            f"derived full body unexpectedly small: {len(body_faces)} faces < {minimum_faces}; "
            f"body_range={[body_start, body_end]} candidate_faces={len(candidate_faces)}"
        )

    used_source_vertices = sorted({vertex for face in body_faces for vertex in face.vertices})
    source_to_compact = {source: compact for compact, source in enumerate(used_source_vertices)}
    compact_vertices = [vertices[source] for source in used_source_vertices]

    used_source_uvs = sorted({uv for face in body_faces for uv in face.texcoords if uv is not None})
    uv_to_compact = {source: compact for compact, source in enumerate(used_source_uvs)}
    compact_uvs = [texcoords[source] for source in used_source_uvs]
    compact_faces = [
        ObjFace(
            tuple(source_to_compact[index] for index in face.vertices),
            tuple(uv_to_compact[uv] if uv is not None else None for uv in face.texcoords),
        )
        for face in body_faces
    ]

    xs = [v[0] for v in compact_vertices]
    ys = [v[1] for v in compact_vertices]
    zs = [v[2] for v in compact_vertices]
    report = {
        "selection_method": "declared_hm08_body_range_then_largest_connected_surface",
        "source_vertices": len(vertices),
        "source_faces": len(faces),
        "declared_body_range": [body_start, body_end],
        "candidate_faces": len(candidate_faces),
        "compact_vertices": len(compact_vertices),
        "compact_faces": len(compact_faces),
        "compact_uvs": len(compact_uvs),
        "compact_actual_bounds": {
            "x": [min(xs), max(xs)],
            "y": [min(ys), max(ys)],
            "z": [min(zs), max(zs)],
        },
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
        raise ValueError(f"target {source_path.name} has no rows inside full body")
    lines = [
        "# Game Asset Forge remapped sparse target",
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


def _load_required_sources(path: str | None) -> set[int]:
    if not path:
        return set()
    packet = json.loads(Path(path).read_text(encoding="utf-8"))
    return {int(value) for value in packet["compact_to_source"]}


def build(args: argparse.Namespace) -> dict[str, object]:
    base = Path(args.base_obj)
    config = Path(args.config_json)
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    targets_dir = output / "targets"
    targets_dir.mkdir(exist_ok=True)

    vertices, texcoords, faces, source_to_compact, extraction = derive_full_body(
        base,
        config,
        minimum_faces=int(getattr(args, "minimum_faces", 5000)),
    )
    body_obj = output / "body.obj"
    write_obj(body_obj, vertices, texcoords, faces)

    compact_to_source = [source for source, _ in sorted(source_to_compact.items(), key=lambda item: item[1])]
    mapping_path = output / "source-index-map.json"
    mapping = {
        "schema": "axm.game-assets.hm08-full-body-source-map.v0.1",
        "source_to_compact": {str(source): compact for source, compact in sorted(source_to_compact.items())},
        "compact_to_source": compact_to_source,
    }
    mapping_path.write_text(json.dumps(mapping, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    target_reports = [
        remap_target(Path(target_path), source_to_compact, targets_dir / Path(target_path).name)
        for target_path in args.target
    ]

    body_sources = set(source_to_compact)
    head_sources = _load_required_sources(getattr(args, "required_head_source_map", None))
    upper_sources = _load_required_sources(getattr(args, "required_upper_source_map", None))
    missing_head = sorted(head_sources - body_sources)
    missing_upper = sorted(upper_sources - body_sources)

    real_threshold = int(getattr(args, "real_threshold", 5000))
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
        "relationship_to_promoted_substrates": {
            "required_head_source_vertices": len(head_sources),
            "missing_head_source_vertices": missing_head,
            "head_source_subset": not missing_head,
            "required_upper_body_source_vertices": len(upper_sources),
            "missing_upper_body_source_vertices": missing_upper,
            "upper_body_source_subset": not missing_upper,
        },
        "extraction": extraction,
        "outputs": {
            "body_obj": {"file": "body.obj", "sha256": _sha256(body_obj)},
            "source_index_map": {"file": "source-index-map.json", "sha256": _sha256(mapping_path)},
            "targets": target_reports,
        },
        "acceptance": {
            "real_hm08_source_used": len(vertices) >= real_threshold and len(faces) >= real_threshold,
            "declared_body_range_used": extraction["selection_method"] == "declared_hm08_body_range_then_largest_connected_surface",
            "source_index_map_complete": len(source_to_compact) == len(vertices),
            "source_uvs_preserved": len(texcoords) > 0,
            "targets_retained": all(int(report["retained_rows"]) > 0 for report in target_reports),
            "promoted_head_source_is_subset": not missing_head,
            "promoted_upper_body_source_is_subset": not missing_upper,
        },
        "truth": {
            "production_body_claim": False,
            "notes": [
                "This is the complete continuous hm08 body source substrate, not final Sentinel anatomy, proportions, rigging, clothing or armor.",
                "Helper eyes/hair/lashes/teeth/tongue/clothing geometry are excluded by the declared MakeHuman body range and remain separately owned layers.",
                "Facial identity targets remain sparse source layers and can be applied on this larger topology using the remapped files."
            ],
        },
    }
    manifest_path = output / "seed-manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    manifest["manifest_sha256"] = _sha256(manifest_path)
    if not all(manifest["acceptance"].values()):
        raise ValueError(f"hm08 full-body acceptance failed: {manifest['acceptance']}")
    return manifest


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser()
    p.add_argument("--base-obj", required=True)
    p.add_argument("--config-json", required=True)
    p.add_argument("--target", action="append", default=[])
    p.add_argument("--required-head-source-map")
    p.add_argument("--required-upper-source-map")
    p.add_argument("--output", required=True)
    p.add_argument("--makehuman-revision", required=True)
    p.add_argument("--mpfb-revision", required=True)
    p.add_argument("--minimum-faces", type=int, default=5000)
    p.add_argument("--real-threshold", type=int, default=5000)
    return p


if __name__ == "__main__":
    result = build(parser().parse_args())
    print(json.dumps({"acceptance": result["acceptance"], "extraction": result["extraction"], "relationships": result["relationship_to_promoted_substrates"]}, indent=2))
