#!/usr/bin/env python3
"""Regression contract for create-only canonical Genome initialization."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent
FORGE = ROOT / "forge.py"


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


def main() -> None:
    with tempfile.TemporaryDirectory() as directory:
        temp = Path(directory)
        existing_output_is_not_rewritten(temp)
        concurrent_initializers_have_one_winner(temp)
    print("Forge create-only Genome initialization tests: PASS")


if __name__ == "__main__":
    main()
