#!/usr/bin/env python3
"""Regression contract for create-only Genome init and its read-only HOLD inspection."""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import forge


ROOT = Path(__file__).resolve().parent
FORGE = ROOT / "forge.py"
INSPECTOR = ROOT / "forge_init_inspector.py"


def request(asset_id: str) -> dict[str, object]:
    return {
        "asset": {
            "id": asset_id,
            "name": asset_id,
            "type": "character",
            "unit_meters": 1.8,
        },
        "targets": {"engines": ["godot"]},
        "budgets": {
            "triangles": {"lod0": 100, "lod1": 50, "lod2": 25, "lod3": 10}
        },
        "quality": {
            "pbr_channels": ["base_color", "normal", "roughness", "metallic"]
        },
    }


def run_init(request_path: Path, output: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(FORGE), "init", str(request_path), str(output)],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


def run_recover(request_path: Path, output: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(FORGE), "recover-init", str(request_path), str(output)],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


def run_inspect(output: Path, *, json_mode: bool = False) -> subprocess.CompletedProcess[str]:
    command = [sys.executable, str(INSPECTOR), str(output)]
    if json_mode:
        command.append("--json")
    return subprocess.run(
        command,
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


def tree_bytes(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def existing_output_is_not_rewritten(temp: Path) -> None:
    first_request = temp / "first.json"
    second_request = temp / "second.json"
    output = temp / "existing-output"
    first_request.write_text(json.dumps(request("first")), encoding="utf-8")
    second_request.write_text(json.dumps(request("second")), encoding="utf-8")

    first = run_init(first_request, output)
    assert first.returncode == 0, first.stderr
    before = tree_bytes(output)
    assert set(before) == {"genome.json", "receipts/000-intake.json"}

    second = run_init(second_request, output)
    assert second.returncode == 2, (second.stdout, second.stderr)
    assert "HOLD AXM_FORGE_INIT_OUTPUT_EXISTS" in second.stderr
    assert tree_bytes(output) == before, "rejected initialization rewrote canonical bytes"
    assert json.loads((output / "genome.json").read_text(encoding="utf-8"))["asset"]["id"] == "first"


def concurrent_initializers_have_one_winner(temp: Path) -> None:
    request_path = temp / "concurrent.json"
    output = temp / "concurrent-output"
    request_path.write_text(json.dumps(request("concurrent")), encoding="utf-8")
    command = [sys.executable, str(FORGE), "init", str(request_path), str(output)]
    processes = [
        subprocess.Popen(command, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        for _ in range(2)
    ]
    results = [process.communicate(timeout=15) for process in processes]
    codes = sorted(process.returncode for process in processes)
    assert codes == [0, 2], [(process.returncode, result) for process, result in zip(processes, results)]
    held = [result for process, result in zip(processes, results) if process.returncode == 2]
    assert len(held) == 1 and "HOLD AXM_FORGE_INIT_OUTPUT_EXISTS" in held[0][1]
    assert set(tree_bytes(output)) == {"genome.json", "receipts/000-intake.json"}

    audit = subprocess.run(
        [sys.executable, str(FORGE), "audit", str(output / "genome.json")],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert audit.returncode == 0, audit.stdout + audit.stderr
    assert "RESULT PASS" in audit.stdout


def exact_genome_only_initialization_can_be_resumed(temp: Path) -> None:
    request_path = temp / "recovery-request.json"
    other_request_path = temp / "other-request.json"
    completed = temp / "completed-source"
    interrupted = temp / "interrupted-output"
    divergent = temp / "divergent-output"
    request_path.write_text(json.dumps(request("recovery")), encoding="utf-8")
    other_request_path.write_text(json.dumps(request("other")), encoding="utf-8")

    created = run_init(request_path, completed)
    assert created.returncode == 0, created.stderr
    interrupted.mkdir()
    shutil.copyfile(completed / "genome.json", interrupted / "genome.json")
    before = tree_bytes(interrupted)
    assert set(before) == {"genome.json"}, "fixture must model interruption after Genome publication"

    wrong_request = run_recover(other_request_path, interrupted)
    assert wrong_request.returncode == 2, (wrong_request.stdout, wrong_request.stderr)
    assert "HOLD AXM_FORGE_INIT_RECOVERY_DIVERGED" in wrong_request.stderr
    assert tree_bytes(interrupted) == before, "divergent recovery changed retained evidence"

    recovered = run_recover(request_path, interrupted)
    assert recovered.returncode == 0, (recovered.stdout, recovered.stderr)
    assert set(tree_bytes(interrupted)) == {"genome.json", "receipts/000-intake.json"}
    assert (interrupted / "genome.json").read_bytes() == before["genome.json"]
    assert (interrupted / "receipts" / "000-intake.json").read_bytes() == (
        completed / "receipts" / "000-intake.json"
    ).read_bytes(), "recovery did not reconstruct the exact initialization receipt"

    repeated = run_recover(request_path, interrupted)
    assert repeated.returncode == 0, (repeated.stdout, repeated.stderr)
    assert "ALREADY_COMPLETE" in repeated.stdout

    shutil.copytree(interrupted, divergent)
    genome_path = divergent / "genome.json"
    genome = json.loads(genome_path.read_text(encoding="utf-8"))
    genome["asset"]["name"] = "tampered but resealed"
    genome.pop("genome_digest")
    genome["genome_digest"] = forge.digest(genome)
    genome_path.write_text(json.dumps(genome, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    divergent_before = tree_bytes(divergent)
    rejected = run_recover(request_path, divergent)
    assert rejected.returncode == 2, (rejected.stdout, rejected.stderr)
    assert "HOLD AXM_FORGE_INIT_RECOVERY_DIVERGED" in rejected.stderr
    assert tree_bytes(divergent) == divergent_before, "rejected recovery rewrote divergent state"


def init_hold_inspection_is_read_only_and_actionable(temp: Path) -> None:
    available = temp / "available-output"
    result = run_inspect(available, json_mode=True)
    assert result.returncode == 0, result.stderr
    available_report = json.loads(result.stdout)
    assert available_report["state"] == "AVAILABLE"
    assert available_report["safe_to_initialize_here"] is True
    assert not available.exists(), "read-only inspection created an available output path"

    request_path = temp / "inspection-request.json"
    request_path.write_text(json.dumps(request("inspection")), encoding="utf-8")
    complete = temp / "complete-output"
    created = run_init(request_path, complete)
    assert created.returncode == 0, created.stderr
    complete_before = tree_bytes(complete)

    human = run_inspect(complete)
    assert human.returncode == 0, human.stderr
    assert "FORGE INIT INSPECTION" in human.stdout
    assert "STATE: ESTABLISHED_INITIALIZATION" in human.stdout
    assert "SAFE TO RUN INIT HERE: NO" in human.stdout
    assert "BOUNDARY: READ ONLY" in human.stdout
    assert tree_bytes(complete) == complete_before, "human inspection changed established state"

    complete_json = run_inspect(complete, json_mode=True)
    complete_report = json.loads(complete_json.stdout)
    assert complete_report["state"] == "ESTABLISHED_INITIALIZATION"
    assert complete_report["facts"]["genome_digest_valid"] is True
    assert complete_report["facts"]["intake_receipt_digest_valid"] is True
    assert complete_report["facts"]["request_digest_bound_to_intake"] is True
    assert complete_report["facts"]["current_genome_is_intake_output"] is True
    assert all(value is False for key, value in complete_report["authority"].items() if key != "read_only")
    assert complete_report["authority"]["read_only"] is True
    assert tree_bytes(complete) == complete_before, "machine inspection changed established state"

    partial = temp / "partial-output"
    partial.mkdir()
    shutil.copyfile(complete / "genome.json", partial / "genome.json")
    partial_before = tree_bytes(partial)
    partial_result = run_inspect(partial, json_mode=True)
    partial_report = json.loads(partial_result.stdout)
    assert partial_report["state"] == "HELD_PARTIAL_INITIALIZATION"
    assert partial_report["safe_to_initialize_here"] is False
    assert tree_bytes(partial) == partial_before, "partial inspection repaired or deleted evidence"

    occupied = temp / "occupied-output"
    occupied.mkdir()
    occupied_result = run_inspect(occupied, json_mode=True)
    assert json.loads(occupied_result.stdout)["state"] == "HELD_OCCUPIED"
    assert tree_bytes(occupied) == {}, "empty occupied directory was mutated"

    non_directory = temp / "occupied-file"
    non_directory.write_text("preserve me\n", encoding="utf-8")
    non_directory_before = non_directory.read_bytes()
    non_directory_result = run_inspect(non_directory, json_mode=True)
    assert json.loads(non_directory_result.stdout)["state"] == "HELD_NOT_DIRECTORY"
    assert non_directory.read_bytes() == non_directory_before

    ambiguous = temp / "ambiguous-output"
    shutil.copytree(complete, ambiguous)
    receipt_path = ambiguous / "receipts" / "000-intake.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["notes"].append("unsealed mutation")
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    ambiguous_before = tree_bytes(ambiguous)
    ambiguous_result = run_inspect(ambiguous, json_mode=True)
    ambiguous_report = json.loads(ambiguous_result.stdout)
    assert ambiguous_report["state"] == "HELD_AMBIGUOUS_INITIALIZATION"
    assert ambiguous_report["facts"]["intake_receipt_digest_valid"] is False
    assert tree_bytes(ambiguous) == ambiguous_before, "ambiguous inspection rewrote suspect evidence"

    evolved = temp / "evolved-output"
    shutil.copytree(complete, evolved)
    genome_path = evolved / "genome.json"
    genome = json.loads(genome_path.read_text(encoding="utf-8"))
    genome.pop("genome_digest")
    genome["pipeline"]["status"] = "post-init-test"
    genome["genome_digest"] = forge.digest(genome)
    genome_path.write_text(json.dumps(genome, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    evolved_before = tree_bytes(evolved)
    evolved_result = run_inspect(evolved, json_mode=True)
    evolved_report = json.loads(evolved_result.stdout)
    assert evolved_report["state"] == "ESTABLISHED_FORGE_STATE"
    assert evolved_report["facts"]["genome_digest_valid"] is True
    assert evolved_report["facts"]["current_genome_is_intake_output"] is False
    assert tree_bytes(evolved) == evolved_before, "inspection rewrote evolved Forge state"


def main() -> None:
    with tempfile.TemporaryDirectory() as directory:
        temp = Path(directory)
        existing_output_is_not_rewritten(temp)
        concurrent_initializers_have_one_winner(temp)
        exact_genome_only_initialization_can_be_resumed(temp)
        init_hold_inspection_is_read_only_and_actionable(temp)
    print("Forge create-only Genome initialization + HOLD inspection tests: PASS")


if __name__ == "__main__":
    main()
