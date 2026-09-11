#!/usr/bin/env python3
"""AXM Game Asset Forge genesis spine.

Truthful orchestration only. This file does not claim high-end generation until
real adapters and in-game evidence exist.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shutil
import stat
import sys
import uuid
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

VERSION = "0.1.0"
INIT_OUTPUT_EXISTS = "AXM_FORGE_INIT_OUTPUT_EXISTS"
INIT_RECOVERY_DIVERGED = "AXM_FORGE_INIT_RECOVERY_DIVERGED"
MAX_INIT_EVIDENCE_BYTES = 64 * 1024 * 1024

STAGES = [
    ("intake", "deterministic"), ("art_direction", "hybrid"),
    ("shape", "hybrid"), ("high_detail", "hybrid"),
    ("retopology", "hybrid"), ("uv", "deterministic"),
    ("bake", "deterministic"), ("materials", "hybrid"),
    ("rig", "hybrid"), ("skinning", "hybrid"),
    ("animation", "hybrid"), ("secondary_motion", "hybrid"),
    ("facial", "hybrid"), ("vfx", "hybrid"),
    ("lod", "deterministic"), ("collision", "deterministic"),
    ("engine_pack", "deterministic"), ("in_game_validation", "hybrid"),
    ("canonize", "deterministic"),
]
KNOWN_STAGES = {stage for stage, _ in STAGES}


class ForgeStateError(RuntimeError):
    """Stable fail-closed error for canonical Forge state transitions."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def canonical_json(data: Any) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def digest(data: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_json(data).encode()).hexdigest()


def load(path: str | Path) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def save(path: str | Path, value: dict[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def json_bytes(value: dict[str, Any]) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


def new_genome(request: dict[str, Any], *, created_at: str | None = None) -> dict[str, Any]:
    genome = {
        "genome_version": VERSION,
        "asset": deepcopy(request["asset"]),
        "targets": deepcopy(request.get("targets", {})),
        "budgets": deepcopy(request.get("budgets", {})),
        "quality": deepcopy(request.get("quality", {})),
        "variants": deepcopy(request.get("variants", [])),
        "source_state": {"artifacts": [], "layers": [], "canonical_stage": "intake"},
        "pipeline": {"attempts": [], "status": "initialized"},
        "provenance": {
            "created_at": created_at or utc_now(),
            "request_digest": digest(request),
            "sources": deepcopy(request.get("sources", [])),
        },
    }
    genome["genome_digest"] = digest(genome)
    return genome


def initial_intake_receipt(genome: dict[str, Any]) -> dict[str, Any]:
    """Derive the intake commit marker from the exact initialized Genome."""
    return receipt(
        "intake", "pass", [genome["provenance"]["request_digest"]], [genome["genome_digest"]],
        {"id": "axm-game-assets", "version": VERSION, "mode": "deterministic"},
        ["Genome initialized. No geometry generation claimed."],
        created_at=genome["provenance"]["created_at"],
    )


def initialize_genome(request: dict[str, Any], output: str | Path) -> Path:
    """Create one new Genome output without replacing existing authority."""
    genome = new_genome(request)
    intake_receipt = initial_intake_receipt(genome)
    out = Path(output)
    out.parent.mkdir(parents=True, exist_ok=True)
    try:
        out.mkdir()
    except FileExistsError as error:
        raise ForgeStateError(
            INIT_OUTPUT_EXISTS,
            f"canonical Genome output already exists: {out}",
        ) from error
    save(out / "genome.json", genome)
    save(out / "receipts" / "000-intake.json", intake_receipt)
    return out / "genome.json"


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, member in pairs:
        if key in value:
            raise ForgeStateError(INIT_RECOVERY_DIVERGED, f"duplicate JSON member: {key}")
        value[key] = member
    return value


def _read_exact_init_json(path: Path) -> tuple[dict[str, Any], bytes]:
    if path.is_symlink():
        raise ForgeStateError(INIT_RECOVERY_DIVERGED, f"refusing symlinked recovery evidence: {path}")
    try:
        metadata = path.stat()
        if not stat.S_ISREG(metadata.st_mode):
            raise ForgeStateError(INIT_RECOVERY_DIVERGED, f"recovery evidence is not a regular file: {path}")
        if metadata.st_size > MAX_INIT_EVIDENCE_BYTES:
            raise ForgeStateError(
                INIT_RECOVERY_DIVERGED,
                f"recovery evidence exceeds {MAX_INIT_EVIDENCE_BYTES} bytes: {path}",
            )
        raw = path.read_bytes()
        value = json.loads(raw.decode("utf-8", errors="strict"), object_pairs_hook=_strict_object)
    except ForgeStateError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ForgeStateError(INIT_RECOVERY_DIVERGED, f"cannot admit recovery evidence {path}: {error}") from error
    if not isinstance(value, dict):
        raise ForgeStateError(INIT_RECOVERY_DIVERGED, f"recovery evidence must be one JSON object: {path}")
    return value, raw


def _sync_directory(path: Path) -> bool:
    try:
        descriptor = os.open(path, os.O_RDONLY)
    except OSError:
        return False
    try:
        os.fsync(descriptor)
        return True
    except OSError:
        return False
    finally:
        os.close(descriptor)


def _publish_create_only_json(path: Path, value: dict[str, Any]) -> bool:
    """Publish one complete commit marker without replacing another actor's file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    stage = path.parent / f".{path.name}.{os.getpid()}.{uuid.uuid4().hex}.stage"
    raw = json_bytes(value)
    descriptor = os.open(stage, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        view = memoryview(raw)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise OSError("short write while staging recovery receipt")
            view = view[written:]
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    try:
        try:
            os.link(stage, path)
            created = True
        except FileExistsError:
            _, existing_raw = _read_exact_init_json(path)
            if existing_raw != raw:
                raise ForgeStateError(
                    INIT_RECOVERY_DIVERGED,
                    f"another actor published a different intake receipt: {path}",
                )
            created = False
        _sync_directory(path.parent)
        return created
    finally:
        try:
            stage.unlink()
        except FileNotFoundError:
            pass


def recover_genome_initialization(request: dict[str, Any], output: str | Path) -> tuple[str, Path]:
    """Complete an exact Genome-only initialization without rewriting canonical bytes."""
    out = Path(output)
    if out.is_symlink() or not out.is_dir():
        raise ForgeStateError(INIT_RECOVERY_DIVERGED, f"recovery output must be one real directory: {out}")
    genome_path = out / "genome.json"
    receipt_directory = out / "receipts"
    receipt_path = receipt_directory / "000-intake.json"
    allowed_files = {genome_path, receipt_path}
    for entry in out.rglob("*"):
        if entry.is_symlink():
            raise ForgeStateError(INIT_RECOVERY_DIVERGED, f"refusing symlinked recovery footprint: {entry}")
        if entry.is_file() and entry not in allowed_files:
            if entry.parent == receipt_directory and entry.name.startswith(".000-intake.json.") and entry.name.endswith(".stage"):
                continue
            raise ForgeStateError(INIT_RECOVERY_DIVERGED, f"unexpected file in recovery footprint: {entry}")
    if not genome_path.exists():
        raise ForgeStateError(INIT_RECOVERY_DIVERGED, f"recoverable Genome is missing: {genome_path}")
    genome, genome_raw = _read_exact_init_json(genome_path)
    provenance = genome.get("provenance")
    created_at = provenance.get("created_at") if isinstance(provenance, dict) else None
    if not isinstance(created_at, str) or not created_at:
        raise ForgeStateError(INIT_RECOVERY_DIVERGED, "Genome does not carry a usable creation identity")
    expected_genome = new_genome(request, created_at=created_at)
    if genome_raw != json_bytes(expected_genome):
        raise ForgeStateError(
            INIT_RECOVERY_DIVERGED,
            "retained Genome is not the exact initialized state derived from the caller-pinned request",
        )
    expected_receipt = initial_intake_receipt(expected_genome)
    if receipt_path.exists() or receipt_path.is_symlink():
        _, receipt_raw = _read_exact_init_json(receipt_path)
        if receipt_raw != json_bytes(expected_receipt):
            raise ForgeStateError(
                INIT_RECOVERY_DIVERGED,
                "existing intake receipt does not exactly match the admitted Genome and request",
            )
        return "ALREADY_COMPLETE", genome_path
    if receipt_directory.exists() and (receipt_directory.is_symlink() or not receipt_directory.is_dir()):
        raise ForgeStateError(INIT_RECOVERY_DIVERGED, f"unsafe intake receipt directory: {receipt_directory}")
    created = _publish_create_only_json(receipt_path, expected_receipt)
    return ("RECOVERED" if created else "ALREADY_COMPLETE"), genome_path


def receipt(stage: str, status: str, inputs: list[str], outputs: list[str], tool: dict[str, Any], notes: list[str] | None = None, *, created_at: str | None = None) -> dict[str, Any]:
    value = {
        "stage": stage, "status": status, "created_at": created_at or utc_now(),
        "inputs": inputs, "outputs": outputs, "tool": tool, "notes": notes or [],
    }
    value["receipt_digest"] = digest(value)
    return value


def audit(genome: dict[str, Any]) -> dict[str, Any]:
    gates: list[dict[str, str]] = []

    def check(ok: bool, gate: str, detail: str) -> None:
        gates.append({"gate": gate, "status": "pass" if ok else "fail", "detail": detail})

    required = ["genome_version", "asset", "targets", "budgets", "quality", "source_state", "pipeline", "provenance", "genome_digest"]
    for key in required:
        check(key in genome, f"required:{key}", f"top-level field {key} must exist")
    asset = genome.get("asset", {})
    check(bool(asset.get("id")), "asset:id", "stable asset id required")
    check(float(asset.get("unit_meters", 0) or 0) > 0, "asset:scale", "positive scale reference required")
    check(bool(genome.get("targets", {}).get("engines")), "targets:engines", "at least one engine target required")
    lods = genome.get("budgets", {}).get("triangles", {})
    ordered = [lods.get(f"lod{i}") for i in range(4) if lods.get(f"lod{i}") is not None]
    check(bool(ordered) and all(a > b for a, b in zip(ordered, ordered[1:])), "lod:monotonic", "triangle budgets must decrease across LODs")
    pbr = set(genome.get("quality", {}).get("pbr_channels", []))
    check({"base_color", "normal", "roughness", "metallic"}.issubset(pbr), "materials:pbr_core", "core PBR channels required")
    fake = [a for a in genome.get("pipeline", {}).get("attempts", []) if a.get("status") == "pass" and a.get("evidence_required") and not a.get("evidence")]
    check(not fake, "receipts:no_evidence_free_pass", "evidence-required stages cannot pass without evidence")
    counts = {state: sum(g["status"] == state for g in gates) for state in ("pass", "fail", "blocked")}
    return {"status": "fail" if counts["fail"] else "pass", "counts": counts, "gates": gates}


def recipe_waves(recipe: dict[str, Any]) -> list[list[str]]:
    nodes = recipe.get("nodes", [])
    if not nodes:
        raise ValueError("recipe needs nodes")
    declared = [node["stage"] for node in nodes]
    if len(declared) != len(set(declared)):
        raise ValueError("duplicate recipe stages")
    unknown = sorted(set(declared) - KNOWN_STAGES)
    if unknown:
        raise ValueError(f"unknown stages: {unknown}")
    remaining = {node["stage"]: set(node.get("needs", [])) for node in nodes}
    for stage, needs in remaining.items():
        missing = needs - set(declared)
        if missing:
            raise ValueError(f"{stage} depends on missing {sorted(missing)}")
    completed: set[str] = set()
    waves: list[list[str]] = []
    while remaining:
        wave = [stage for stage in declared if stage in remaining and remaining[stage].issubset(completed)]
        if not wave:
            raise ValueError("recipe dependency cycle")
        waves.append(wave)
        for stage in wave:
            completed.add(stage)
            del remaining[stage]
    return waves


def evaluate_adapter(adapter: dict[str, Any], hardware: dict[str, Any], jurisdiction: str | None) -> tuple[str, list[str]]:
    status = adapter.get("status", "research_only")
    reasons: list[str] = []
    blocked = {x.upper() for x in adapter.get("blocked_jurisdictions", [])}
    if jurisdiction and jurisdiction.upper() in blocked:
        status = "blocked"
        reasons.append(f"jurisdiction {jurisdiction.upper()} blocked by recorded license/policy")
    vram = float(hardware.get("vram_gb", 0) or 0)
    min_vram = float(adapter.get("min_vram_gb", 0) or 0)
    if min_vram > vram:
        status = "blocked"
        reasons.append(f"needs {min_vram:g} GB VRAM, have {vram:g} GB")
    if adapter.get("network_required") and hardware.get("offline_only"):
        status = "blocked"
        reasons.append("network required but profile is offline-only")
    if not reasons:
        reasons.append("no recorded hardware/jurisdiction blocker")
    return status, reasons


def doctor() -> dict[str, Any]:
    tools = []
    for executable in ("blender", "godot", "node", "ffmpeg", "git"):
        path = shutil.which(executable)
        tools.append({"id": executable, "status": "available" if path else "unavailable", "path": path})
    return {"platform": platform.platform(), "python": platform.python_version(), "tools": tools}


def cmd_init(args: argparse.Namespace) -> int:
    request = load(args.request)
    print(initialize_genome(request, args.output))
    return 0


def cmd_recover_init(args: argparse.Namespace) -> int:
    status, genome_path = recover_genome_initialization(load(args.request), args.output)
    print(status, genome_path)
    return 0


def cmd_plan(args: argparse.Namespace) -> int:
    for index, wave in enumerate(recipe_waves(load(args.recipe))):
        print(f"WAVE {index:02d}  " + ", ".join(wave))
    return 0


def cmd_audit(args: argparse.Namespace) -> int:
    report = audit(load(args.genome))
    for gate in report["gates"]:
        print(f"{gate['status'].upper():7} {gate['gate']}: {gate['detail']}")
    print("RESULT", report["status"].upper(), report["counts"])
    return int(report["status"] == "fail")


def cmd_doctor(_: argparse.Namespace) -> int:
    report = doctor()
    print(f"Python {report['python']} | {report['platform']}")
    for tool in report["tools"]:
        print(f"{tool['status'].upper():11} {tool['id']:<8} {tool['path'] or 'not found'}")
    return 0


def cmd_capability(args: argparse.Namespace) -> int:
    registry, hardware = load(args.registry), load(args.hardware)
    found = False
    for adapter in registry.get("adapters", []):
        if args.capability not in adapter.get("capabilities", []):
            continue
        found = True
        status, reasons = evaluate_adapter(adapter, hardware, args.jurisdiction)
        print(f"{status.upper():20} {adapter['id']}")
        for reason in reasons:
            print("  -", reason)
    return 0 if found else 2


def cmd_self_test(_: argparse.Namespace) -> int:
    request = {
        "asset": {"id": "test", "name": "Test", "type": "character", "unit_meters": 1.8},
        "targets": {"engines": ["godot"]},
        "budgets": {"triangles": {"lod0": 100, "lod1": 50, "lod2": 25, "lod3": 10}},
        "quality": {"pbr_channels": ["base_color", "normal", "roughness", "metallic"]},
    }
    assert audit(new_genome(request))["status"] == "pass"
    try:
        recipe_waves({"nodes": [{"stage": "intake", "needs": ["art_direction"]}, {"stage": "art_direction", "needs": ["intake"]}]})
    except ValueError:
        pass
    else:
        raise AssertionError("cycle must fail")
    status, _ = evaluate_adapter({"id": "x", "blocked_jurisdictions": ["EU"]}, {"vram_gb": 99}, "EU")
    assert status == "blocked"
    print("SELF-TEST PASS")
    return 0


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="forge.py")
    sub = root.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("init"); p.add_argument("request"); p.add_argument("output"); p.set_defaults(fn=cmd_init)
    p = sub.add_parser("recover-init"); p.add_argument("request"); p.add_argument("output"); p.set_defaults(fn=cmd_recover_init)
    p = sub.add_parser("plan"); p.add_argument("recipe"); p.set_defaults(fn=cmd_plan)
    p = sub.add_parser("audit"); p.add_argument("genome"); p.set_defaults(fn=cmd_audit)
    p = sub.add_parser("doctor"); p.set_defaults(fn=cmd_doctor)
    p = sub.add_parser("capability"); p.add_argument("capability"); p.add_argument("--registry", default="capability-registry.json"); p.add_argument("--hardware", required=True); p.add_argument("--jurisdiction"); p.set_defaults(fn=cmd_capability)
    p = sub.add_parser("self-test"); p.set_defaults(fn=cmd_self_test)
    return root


if __name__ == "__main__":
    args = parser().parse_args()
    try:
        raise SystemExit(args.fn(args))
    except ForgeStateError as error:
        print(f"HOLD {error.code}: {error}", file=sys.stderr)
        raise SystemExit(2) from error
