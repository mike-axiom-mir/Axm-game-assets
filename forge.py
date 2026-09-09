#!/usr/bin/env python3
"""AXM Game Asset Forge genesis spine.

Truthful orchestration only. This file does not claim high-end generation until
real adapters and in-game evidence exist.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
import shutil
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

VERSION = "0.1.0"

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


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def canonical_json(data: Any) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def digest(data: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_json(data).encode()).hexdigest()


def verify_embedded_digest(value: dict[str, Any], field: str) -> bool:
    stored = value.get(field)
    if not isinstance(stored, str):
        return False
    payload = deepcopy(value)
    payload.pop(field, None)
    return stored == digest(payload)


def load(path: str | Path) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def save(path: str | Path, value: dict[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def new_genome(request: dict[str, Any]) -> dict[str, Any]:
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
            "created_at": utc_now(),
            "request_digest": digest(request),
            "sources": deepcopy(request.get("sources", [])),
        },
    }
    genome["genome_digest"] = digest(genome)
    return genome


def receipt(stage: str, status: str, inputs: list[str], outputs: list[str], tool: dict[str, Any], notes: list[str] | None = None) -> dict[str, Any]:
    value = {
        "stage": stage, "status": status, "created_at": utc_now(),
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
    check(
        verify_embedded_digest(genome, "genome_digest"),
        "genome:digest",
        "genome_digest must bind the complete canonical genome payload",
    )
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
    genome = new_genome(request)
    out = Path(args.output)
    save(out / "genome.json", genome)
    save(out / "receipts" / "000-intake.json", receipt(
        "intake", "pass", [genome["provenance"]["request_digest"]], [genome["genome_digest"]],
        {"id": "axm-game-assets", "version": VERSION, "mode": "deterministic"},
        ["Genome initialized. No geometry generation claimed."],
    ))
    print(out / "genome.json")
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
    genome = new_genome(request)
    assert audit(genome)["status"] == "pass"
    tampered = deepcopy(genome)
    tampered["asset"]["name"] = "Tampered after sealing"
    tampered_report = audit(tampered)
    assert tampered_report["status"] == "fail"
    assert any(gate["gate"] == "genome:digest" and gate["status"] == "fail" for gate in tampered_report["gates"])
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
    p = sub.add_parser("plan"); p.add_argument("recipe"); p.set_defaults(fn=cmd_plan)
    p = sub.add_parser("audit"); p.add_argument("genome"); p.set_defaults(fn=cmd_audit)
    p = sub.add_parser("doctor"); p.set_defaults(fn=cmd_doctor)
    p = sub.add_parser("capability"); p.add_argument("capability"); p.add_argument("--registry", default="capability-registry.json"); p.add_argument("--hardware", required=True); p.add_argument("--jurisdiction"); p.set_defaults(fn=cmd_capability)
    p = sub.add_parser("self-test"); p.set_defaults(fn=cmd_self_test)
    return root


if __name__ == "__main__":
    args = parser().parse_args()
    raise SystemExit(args.fn(args))
