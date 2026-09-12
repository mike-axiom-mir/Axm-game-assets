#!/usr/bin/env python3
"""Admit an AXM Universal Creation 3D forge result as a proposal-only candidate.

This bridge deliberately consumes only the public artifact contract emitted by
axm-universal-creation. It does not import Universal Creation source, trust its
acceptance label as Game Asset Forge acceptance, mutate a Game Asset Genome, or
grant release / merge / CANON authority.

Expected candidate directory:
- forge-request.json
- asset-manifest.json
- forge-receipt.json
- manifest-declared source, LOD/collision GLBs, and PNG render proofs

The bridge re-reads and hashes the actual bytes, performs a small independent
GLB container check, checks PNG dimensions, verifies identity continuity across
request/manifest/receipt, and emits a portable proposal receipt.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import stat
import struct
import sys
from typing import Any, Iterable

PROPOSAL_SCHEMA = "axm.game-assets.universal-creation-3d-proposal/v0.1"
REQUEST_SCHEMA = "axm.3d-forge-request/v0.1"
RECEIPT_SCHEMA = "axm.3d-forge-receipt/v0.1"
PROVIDER_REPOSITORY = "mike-axiom-mir/axm-universal-creation"
CONSUMER_REPOSITORY = "mike-axiom-mir/Axm-game-assets"

MAX_METADATA_BYTES = 4 * 1024 * 1024
MAX_ARTIFACT_BYTES = 256 * 1024 * 1024
MAX_TOTAL_ARTIFACT_BYTES = 1024 * 1024 * 1024
MAX_RENDER_PROOFS = 32
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
GLB_MAGIC = b"glTF"
GLB_JSON = 0x4E4F534A
GLB_BIN = 0x004E4942

REQUIRED_EXPORTS = ("lod0", "lod1", "lod2", "collision")


class UniversalCreationIngressError(RuntimeError):
    def __init__(self, code: str, detail: str):
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


def _sha256_bytes(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def _strict_object_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise UniversalCreationIngressError("DUPLICATE_JSON_KEY", key)
        out[key] = value
    return out


def _read_json_object(path: Path, *, label: str) -> tuple[dict[str, Any], bytes]:
    data = _read_regular_file(path, label=label, max_bytes=MAX_METADATA_BYTES)
    try:
        value = json.loads(data.decode("utf-8"), object_pairs_hook=_strict_object_pairs)
    except UniversalCreationIngressError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise UniversalCreationIngressError(
            "INVALID_JSON", f"{label} is not valid UTF-8 JSON: {exc}"
        ) from exc
    if not isinstance(value, dict):
        raise UniversalCreationIngressError("JSON_NOT_OBJECT", label)
    return value, data


def _read_regular_file(
    path: Path, *, label: str, max_bytes: int | None = None
) -> bytes:
    try:
        info = path.lstat()
    except OSError as exc:
        raise UniversalCreationIngressError(
            "MISSING_FILE", f"{label}: {path}: {exc}"
        ) from exc
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        raise UniversalCreationIngressError(
            "UNSAFE_FILE", f"{label} is not a regular non-symlink file: {path}"
        )
    if max_bytes is not None and info.st_size > max_bytes:
        raise UniversalCreationIngressError(
            "FILE_TOO_LARGE", f"{label} exceeds {max_bytes} bytes: {path}"
        )
    try:
        return path.read_bytes()
    except OSError as exc:
        raise UniversalCreationIngressError(
            "READ_FAILED", f"{label}: {path}: {exc}"
        ) from exc


def _candidate_root(path: str | Path) -> Path:
    root = Path(path)
    try:
        info = root.lstat()
    except OSError as exc:
        raise UniversalCreationIngressError(
            "CANDIDATE_MISSING", f"{root}: {exc}"
        ) from exc
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
        raise UniversalCreationIngressError(
            "UNSAFE_CANDIDATE_ROOT", f"candidate root must be a real directory: {root}"
        )
    return root.resolve()


def _safe_relative(value: Any, *, label: str) -> PurePosixPath:
    if not isinstance(value, str) or not value or "\\" in value:
        raise UniversalCreationIngressError(
            "UNSAFE_PATH", f"{label} must be one relative POSIX path"
        )
    raw = value.split("/")
    parsed = PurePosixPath(value)
    if (
        parsed.is_absolute()
        or any(part in {"", ".", ".."} for part in raw)
        or parsed.as_posix() != value
    ):
        raise UniversalCreationIngressError(
            "UNSAFE_PATH", f"{label}: {value!r}"
        )
    return parsed


def _member_path(root: Path, relative: Any, *, label: str) -> Path:
    parsed = _safe_relative(relative, label=label)
    current = root
    for part in parsed.parts:
        current = current / part
        try:
            if current.is_symlink():
                raise UniversalCreationIngressError(
                    "UNSAFE_PATH", f"{label} crosses symlink: {relative!r}"
                )
        except OSError as exc:
            raise UniversalCreationIngressError(
                "UNSAFE_PATH", f"{label}: cannot inspect {current}: {exc}"
            ) from exc
    try:
        resolved = current.resolve(strict=False)
        resolved.relative_to(root)
    except (OSError, ValueError) as exc:
        raise UniversalCreationIngressError(
            "UNSAFE_PATH", f"{label} escapes candidate root: {relative!r}"
        ) from exc
    return current


def _normalize_digest(value: Any, *, label: str) -> str:
    if not isinstance(value, str):
        raise UniversalCreationIngressError("INVALID_DIGEST", label)
    text = value.casefold()
    if text.startswith("sha256:"):
        text = text[7:]
    if len(text) != 64 or any(ch not in "0123456789abcdef" for ch in text):
        raise UniversalCreationIngressError(
            "INVALID_DIGEST", f"{label} is not SHA-256 shaped"
        )
    return "sha256:" + text


def _artifact_record(
    root: Path,
    entry: Any,
    *,
    label: str,
    max_bytes: int = MAX_ARTIFACT_BYTES,
) -> tuple[dict[str, Any], bytes]:
    if not isinstance(entry, dict):
        raise UniversalCreationIngressError(
            "INVALID_ARTIFACT_ENTRY", f"{label} must be an object"
        )
    relative = entry.get("path")
    path = _member_path(root, relative, label=f"{label}.path")
    data = _read_regular_file(path, label=label, max_bytes=max_bytes)
    actual_digest = _sha256_bytes(data)
    expected_digest = _normalize_digest(entry.get("sha256"), label=f"{label}.sha256")
    if actual_digest != expected_digest:
        raise UniversalCreationIngressError(
            "ARTIFACT_DIGEST_DRIFT",
            f"{label} digest differs from manifest: {relative}",
        )
    if "bytes" in entry:
        declared_bytes = entry.get("bytes")
        if (
            not isinstance(declared_bytes, int)
            or isinstance(declared_bytes, bool)
            or declared_bytes != len(data)
        ):
            raise UniversalCreationIngressError(
                "ARTIFACT_SIZE_DRIFT",
                f"{label} byte count differs from manifest: {relative}",
            )
    return {
        "path": str(relative),
        "sha256": actual_digest,
        "bytes": len(data),
    }, data


def _glb_identity(data: bytes, *, label: str) -> dict[str, Any]:
    if len(data) < 20:
        raise UniversalCreationIngressError(
            "INVALID_GLB", f"{label} is shorter than a GLB header plus first chunk"
        )
    magic, version, total = struct.unpack_from("<4sII", data, 0)
    if magic != GLB_MAGIC or version != 2 or total != len(data):
        raise UniversalCreationIngressError(
            "INVALID_GLB", f"{label} has an invalid GLB v2 header"
        )
    offset = 12
    chunk_count = 0
    json_document: dict[str, Any] | None = None
    seen_json = False
    while offset < len(data):
        if offset + 8 > len(data):
            raise UniversalCreationIngressError(
                "INVALID_GLB", f"{label} ends inside a chunk header"
            )
        length, kind = struct.unpack_from("<II", data, offset)
        offset += 8
        end = offset + length
        if end > len(data):
            raise UniversalCreationIngressError(
                "INVALID_GLB", f"{label} chunk exceeds file length"
            )
        payload = data[offset:end]
        if chunk_count == 0 and kind != GLB_JSON:
            raise UniversalCreationIngressError(
                "INVALID_GLB", f"{label} first chunk is not JSON"
            )
        if kind == GLB_JSON:
            if seen_json:
                raise UniversalCreationIngressError(
                    "INVALID_GLB", f"{label} contains multiple JSON chunks"
                )
            try:
                parsed = json.loads(
                    payload.rstrip(b" \t\r\n\x00").decode("utf-8"),
                    object_pairs_hook=_strict_object_pairs,
                )
            except UniversalCreationIngressError:
                raise
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise UniversalCreationIngressError(
                    "INVALID_GLB", f"{label} JSON chunk is invalid: {exc}"
                ) from exc
            if not isinstance(parsed, dict):
                raise UniversalCreationIngressError(
                    "INVALID_GLB", f"{label} JSON chunk is not an object"
                )
            if parsed.get("asset", {}).get("version") != "2.0":
                raise UniversalCreationIngressError(
                    "INVALID_GLB", f"{label} glTF asset.version is not 2.0"
                )
            json_document = parsed
            seen_json = True
        elif kind != GLB_BIN:
            # glTF 2.0 permits extension chunks; their presence is evidence only,
            # not rejection, so long as the container remains structurally bounded.
            pass
        offset = end
        chunk_count += 1
    if offset != len(data) or json_document is None:
        raise UniversalCreationIngressError(
            "INVALID_GLB", f"{label} has no valid JSON chunk"
        )
    return {
        "container": "glb",
        "version": 2,
        "chunks": chunk_count,
        "meshes_declared": len(json_document.get("meshes", []))
        if isinstance(json_document.get("meshes"), list)
        else None,
        "materials_declared": len(json_document.get("materials", []))
        if isinstance(json_document.get("materials"), list)
        else None,
        "animations_declared": len(json_document.get("animations", []))
        if isinstance(json_document.get("animations"), list)
        else None,
        "skins_declared": len(json_document.get("skins", []))
        if isinstance(json_document.get("skins"), list)
        else None,
    }


def _png_identity(data: bytes, *, label: str) -> dict[str, Any]:
    if len(data) < 24 or data[:8] != PNG_SIGNATURE or data[12:16] != b"IHDR":
        raise UniversalCreationIngressError(
            "INVALID_PNG", f"{label} is not a PNG with an IHDR header"
        )
    width, height = struct.unpack(">II", data[16:24])
    if width <= 0 or height <= 0 or width > 16384 or height > 16384:
        raise UniversalCreationIngressError(
            "INVALID_PNG", f"{label} has unsupported dimensions {width}x{height}"
        )
    return {"width": width, "height": height, "mime": "image/png"}


def _angles_summary(proofs: list[dict[str, Any]]) -> dict[str, Any]:
    angles: list[float] = []
    for proof in proofs:
        raw = proof.get("angle_degrees")
        if isinstance(raw, bool) or not isinstance(raw, (int, float)):
            return {
                "status": "HOLD",
                "reason": "one or more render proofs have no numeric angle_degrees",
                "proof_count": len(proofs),
            }
        angle = float(raw) % 360.0
        angles.append(angle)
    unique = sorted(set(angles))
    if len(unique) < 2:
        max_gap = 360.0
    else:
        gaps = [
            unique[index + 1] - unique[index]
            for index in range(len(unique) - 1)
        ]
        gaps.append(360.0 - unique[-1] + unique[0])
        max_gap = max(gaps)
    passes = len(unique) >= 4 and max_gap <= 135.0
    return {
        "status": "PASS" if passes else "HOLD",
        "proof_count": len(proofs),
        "distinct_angles": unique,
        "max_circular_gap_degrees": round(max_gap, 6),
        "criterion": "at least four distinct views and max circular gap <= 135 degrees",
    }


def _iter_total_bytes(records: Iterable[dict[str, Any]]) -> int:
    return sum(int(record["bytes"]) for record in records)


def build_universal_creation_proposal(
    candidate: str | Path,
    *,
    expected_asset_id: str | None = None,
) -> dict[str, Any]:
    root = _candidate_root(candidate)

    request, request_bytes = _read_json_object(
        root / "forge-request.json", label="forge-request.json"
    )
    manifest, manifest_bytes = _read_json_object(
        root / "asset-manifest.json", label="asset-manifest.json"
    )
    receipt, receipt_bytes = _read_json_object(
        root / "forge-receipt.json", label="forge-receipt.json"
    )

    if request.get("schema") != REQUEST_SCHEMA:
        raise UniversalCreationIngressError(
            "UNSUPPORTED_REQUEST_SCHEMA", repr(request.get("schema"))
        )
    if receipt.get("schema") != RECEIPT_SCHEMA:
        raise UniversalCreationIngressError(
            "UNSUPPORTED_RECEIPT_SCHEMA", repr(receipt.get("schema"))
        )
    if receipt.get("truth_status") != "BLENDER_FORGE_EXECUTED_AND_GLB_DECODED":
        raise UniversalCreationIngressError(
            "UNSUPPORTED_RECEIPT_STATE", repr(receipt.get("truth_status"))
        )

    asset_id = request.get("asset_id")
    if not isinstance(asset_id, str) or not asset_id.strip():
        raise UniversalCreationIngressError(
            "INVALID_ASSET_ID", "forge request has no asset_id"
        )
    if manifest.get("asset_id") != asset_id or receipt.get("asset_id") != asset_id:
        raise UniversalCreationIngressError(
            "ASSET_IDENTITY_DRIFT",
            "request, manifest, and receipt do not name the same asset",
        )
    if expected_asset_id is not None and asset_id != expected_asset_id:
        raise UniversalCreationIngressError(
            "CONSUMER_ASSET_ID_MISMATCH",
            f"expected {expected_asset_id!r}, received {asset_id!r}",
        )

    source_entry = manifest.get("source")
    source_record, _ = _artifact_record(
        root, source_entry, label="manifest.source"
    )

    exports = manifest.get("exports")
    if not isinstance(exports, dict):
        raise UniversalCreationIngressError(
            "EXPORTS_MISSING", "asset-manifest.json has no exports object"
        )
    export_records: dict[str, Any] = {}
    total_records: list[dict[str, Any]] = [source_record]
    for name in REQUIRED_EXPORTS:
        if name not in exports:
            raise UniversalCreationIngressError(
                "EXPORT_MISSING", f"required export {name!r} is absent"
            )
        record, data = _artifact_record(
            root, exports[name], label=f"manifest.exports.{name}"
        )
        record["inspection"] = _glb_identity(data, label=f"export {name}")
        export_records[name] = record
        total_records.append(record)

    proofs = manifest.get("render_proofs")
    if not isinstance(proofs, list) or not proofs:
        raise UniversalCreationIngressError(
            "RENDER_PROOFS_MISSING", "manifest requires at least one render proof"
        )
    if len(proofs) > MAX_RENDER_PROOFS:
        raise UniversalCreationIngressError(
            "TOO_MANY_RENDER_PROOFS",
            f"{len(proofs)} exceeds {MAX_RENDER_PROOFS}",
        )
    proof_records: list[dict[str, Any]] = []
    for index, entry in enumerate(proofs):
        record, data = _artifact_record(
            root, entry, label=f"manifest.render_proofs[{index}]"
        )
        record.update(_png_identity(data, label=f"render proof {index}"))
        if isinstance(entry, dict) and "angle_degrees" in entry:
            record["angle_degrees"] = entry["angle_degrees"]
        proof_records.append(record)
        total_records.append(record)

    if receipt.get("render_proofs") != proofs:
        raise UniversalCreationIngressError(
            "RECEIPT_PROOF_DRIFT",
            "forge receipt render_proofs do not exactly match the manifest",
        )

    total_bytes = _iter_total_bytes(total_records)
    if total_bytes > MAX_TOTAL_ARTIFACT_BYTES:
        raise UniversalCreationIngressError(
            "CANDIDATE_TOO_LARGE",
            f"declared source/exports/proofs total {total_bytes} bytes",
        )

    metadata = {
        "forge-request.json": {
            "sha256": _sha256_bytes(request_bytes),
            "bytes": len(request_bytes),
        },
        "asset-manifest.json": {
            "sha256": _sha256_bytes(manifest_bytes),
            "bytes": len(manifest_bytes),
        },
        "forge-receipt.json": {
            "sha256": _sha256_bytes(receipt_bytes),
            "bytes": len(receipt_bytes),
        },
    }

    expression_intent = {
        "archetype": request.get("archetype"),
        "faction": request.get("faction"),
        "scale_meters": request.get("scale_meters"),
        "palette": request.get("palette"),
        "quality": request.get("quality"),
        "loadout": request.get("loadout"),
        "context_key": request.get("context_key"),
        "criteria": list(request.get("criteria", []))
        if isinstance(request.get("criteria"), list)
        else [],
        "constraints": list(request.get("constraints", []))
        if isinstance(request.get("constraints"), list)
        else [],
        "avoid": list(request.get("avoid", []))
        if isinstance(request.get("avoid"), list)
        else [],
        "technical_requirements": dict(request.get("technical_requirements", {}))
        if isinstance(request.get("technical_requirements"), dict)
        else {},
        "render": dict(request.get("render", {}))
        if isinstance(request.get("render"), dict)
        else {},
    }

    candidate_binding = {
        "asset_id": asset_id,
        "metadata": metadata,
        "source": source_record,
        "exports": export_records,
        "render_proofs": proof_records,
    }
    candidate_digest = _sha256_bytes(_canonical_json(candidate_binding))
    angles = _angles_summary(proof_records)

    proposal: dict[str, Any] = {
        "schema": PROPOSAL_SCHEMA,
        "status": "PROPOSAL_ONLY",
        "asset": {
            "id": asset_id,
            "provider_candidate_sha256": candidate_digest,
        },
        "provider": {
            "repository": PROVIDER_REPOSITORY,
            "request_schema": REQUEST_SCHEMA,
            "receipt_schema": RECEIPT_SCHEMA,
            "truth_status": receipt.get("truth_status"),
        },
        "consumer": {
            "repository": CONSUMER_REPOSITORY,
            "role": "external_3d_candidate",
        },
        "verified_metadata": metadata,
        "verified_source": source_record,
        "verified_exports": export_records,
        "verified_render_proofs": proof_records,
        "review_readiness": {
            "multi_angle_distribution": angles,
            "visual_acceptance": "NOT_GRANTED",
            "game_asset_acceptance": "NOT_GRANTED",
        },
        "expression_intent": expression_intent,
        "upstream_claims": {
            "acceptance": receipt.get("acceptance"),
            "spatial_contract_review": receipt.get("spatial_contract_review"),
            "note": (
                "Preserved as provider evidence only; Game Asset Forge does not "
                "inherit the provider's pass/fail authority."
            ),
        },
        "authority": {
            "automatic_install": False,
            "automatic_selection": False,
            "genome_mutation": False,
            "source_state_mutation": False,
            "visual_approval": False,
            "runtime_adoption": False,
            "release": False,
            "merge": False,
            "canon": False,
        },
        "truth_boundary": {
            "proven_here": [
                "request/manifest/receipt identity continuity",
                "exact SHA-256 identity of declared source, GLB exports, and PNG proofs",
                "safe in-tree non-symlink artifact paths",
                "bounded GLB v2 container structure",
                "PNG proof dimensions",
                "multi-angle proof distribution when proof angles are declared",
            ],
            "not_proven": [
                "visual quality or AAA quality",
                "Game Asset Genome compatibility",
                "topology or collision fitness beyond the bounded GLB container check",
                "rigging, skinning, deformation, animation, or contact quality",
                "engine import, gameplay behavior, or performance",
                "authorship, provenance, or license fitness beyond retained provider metadata",
                "release, merge, or CANON",
            ],
        },
    }
    proposal["proposal_digest"] = _sha256_bytes(_canonical_json(proposal))
    return proposal


def write_proposal(path: str | Path, proposal: dict[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(proposal, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    try:
        with target.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(payload)
    except FileExistsError as exc:
        raise UniversalCreationIngressError(
            "PROPOSAL_EXISTS", f"refusing to overwrite {target}"
        ) from exc
    except OSError as exc:
        raise UniversalCreationIngressError(
            "PROPOSAL_WRITE_FAILED", f"{target}: {exc}"
        ) from exc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Verify one AXM Universal Creation 3D forge directory and emit a "
            "proposal-only Game Asset Forge ingress receipt."
        )
    )
    parser.add_argument("--candidate", required=True, type=Path)
    parser.add_argument("--proposal", required=True, type=Path)
    parser.add_argument("--expected-asset-id")
    args = parser.parse_args(argv)
    try:
        proposal = build_universal_creation_proposal(
            args.candidate, expected_asset_id=args.expected_asset_id
        )
        write_proposal(args.proposal, proposal)
    except UniversalCreationIngressError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print(json.dumps(proposal, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
