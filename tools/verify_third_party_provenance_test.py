#!/usr/bin/env python3
"""Adversarial regression for the repository third-party provenance boundary."""
from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory

REPO_ROOT = Path(__file__).resolve().parents[1]
VERIFIER = REPO_ROOT / "tools" / "verify_third_party_provenance.py"

ASSET_LICENSE_BLOB = "f3ede1fc3318f8d794e2cb51924186c62f02f71a"
CODE_LICENSE_BLOB = "4ef32f0833975b98cb4080343c8fd60ab6d0f88c"
BASE_OBJ_BLOB = "d26635e9326e3cca30778fd7b9c00062b03cce09"
NOSE_TARGET_BLOB = "db108799ff4614f32bb33f5e7ae4781a2a82349c"
MAKEHUMAN_REVISION = "a8bc2d54ff0ac92e78ff71431b1023eda42bf482"


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def ledger_payload() -> dict[str, object]:
    return {
        "schema": "axm-third-party-v1",
        "repository": "Axm-game-assets",
        "project_license": "Apache-2.0",
        "audit": {"status": "baseline", "complete": False, "note": "fixture"},
        "entries": [
            {
                "id": "makehuman-hm08-seed",
                "kind": "asset-data",
                "role": "optional-human-seed-topology-and-target-data",
                "source": "MakeHuman hm08 assets as pinned by repository research/seed manifest",
                "license": "CC0-1.0",
                "license_verified": True,
                "code_imported": False,
                "canonical_state_owner": "AXM after explicit import",
                "provenance_required": True,
                "provenance": {
                    "research_record": "research/MAKEHUMAN_CC0_SEED.md",
                    "source_repository": "https://github.com/makehumancommunity/makehuman",
                    "captured": "2026-09-07",
                    "makehuman_revision": MAKEHUMAN_REVISION,
                    "asset_license": {
                        "path": "LICENSE.ASSETS.md",
                        "declared_license": "CC0-1.0",
                        "git_blob_sha1": ASSET_LICENSE_BLOB,
                    },
                    "application_license": {
                        "path": "LICENSE.CODE.md",
                        "declared_license": "GNU AGPL v3",
                        "git_blob_sha1": CODE_LICENSE_BLOB,
                    },
                    "base_obj": {
                        "path": "makehuman/data/3dobjs/base.obj",
                        "git_blob_sha1": BASE_OBJ_BLOB,
                    },
                    "pinned_targets": {
                        "nose-width1-incr.target": {
                            "path": "makehuman/data/targets/nose/nose-width1-incr.target",
                            "git_blob_sha1": NOSE_TARGET_BLOB,
                        }
                    },
                    "seed_manifests": ["seed_data/hm08_head_v0.1/seed-manifest.json"],
                },
            }
        ],
        "research_only_policy": "fixture",
    }


def seed_manifest_payload() -> dict[str, object]:
    return {
        "schema": "axm.game-assets.hm08-head-seed.v0.1",
        "source": {
            "license_record": "MakeHuman base mesh/targets: CC0 source data; no MakeHuman application code is imported.",
            "makehuman_base_obj_git_blob_sha1": BASE_OBJ_BLOB,
            "makehuman_revision": MAKEHUMAN_REVISION,
        },
        "outputs": {
            "targets": [
                {
                    "name": "nose-width1-incr.target",
                    "source_git_blob_sha1": NOSE_TARGET_BLOB,
                }
            ]
        },
    }


def make_fixture(root: Path) -> None:
    write_json(root / "THIRD_PARTY.json", ledger_payload())
    record = "\n".join(
        [
            "# MakeHuman evidence fixture",
            ASSET_LICENSE_BLOB,
            CODE_LICENSE_BLOB,
            BASE_OBJ_BLOB,
            NOSE_TARGET_BLOB,
            "",
        ]
    )
    (root / "research").mkdir(parents=True, exist_ok=True)
    (root / "research" / "MAKEHUMAN_CC0_SEED.md").write_text(record, encoding="utf-8")
    write_json(root / "seed_data" / "hm08_head_v0.1" / "seed-manifest.json", seed_manifest_payload())


def run_verifier(root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(VERIFIER), "--repo-root", str(root)],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def require_rejected(root: Path, code: str) -> None:
    proc = run_verifier(root)
    assert proc.returncode == 2, (code, proc.returncode, proc.stdout, proc.stderr)
    assert code in proc.stderr, (code, proc.stderr)


def run() -> None:
    checks = 0
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        make_fixture(root)
        proc = run_verifier(root)
        assert proc.returncode == 0, (proc.returncode, proc.stdout, proc.stderr)
        checks += 1

        payload = ledger_payload()
        payload["entries"][0]["license"] = "Proprietary-9.9"  # type: ignore[index]
        write_json(root / "THIRD_PARTY.json", payload)
        require_rejected(root, "LICENSE_EVIDENCE_MISMATCH")
        checks += 1

        make_fixture(root)
        payload = ledger_payload()
        del payload["entries"][0]["provenance"]["asset_license"]["git_blob_sha1"]  # type: ignore[index]
        write_json(root / "THIRD_PARTY.json", payload)
        require_rejected(root, "EVIDENCE_PIN_INVALID")
        checks += 1

        make_fixture(root)
        write_json(root / "seed_data" / "hm08_extra_v9" / "seed-manifest.json", seed_manifest_payload())
        require_rejected(root, "SEED_MANIFEST_SET_DRIFT")
        checks += 1

        make_fixture(root)
        manifest = seed_manifest_payload()
        manifest["source"]["makehuman_base_obj_git_blob_sha1"] = "0" * 40  # type: ignore[index]
        write_json(root / "seed_data" / "hm08_head_v0.1" / "seed-manifest.json", manifest)
        require_rejected(root, "BASE_SOURCE_MISMATCH")
        checks += 1

        make_fixture(root)
        manifest = seed_manifest_payload()
        manifest["outputs"]["targets"][0]["source_git_blob_sha1"] = "1" * 40  # type: ignore[index]
        write_json(root / "seed_data" / "hm08_head_v0.1" / "seed-manifest.json", manifest)
        require_rejected(root, "TARGET_SOURCE_MISMATCH")
        checks += 1

        make_fixture(root)
        record = root / "research" / "MAKEHUMAN_CC0_SEED.md"
        record.write_text(record.read_text(encoding="utf-8").replace(CODE_LICENSE_BLOB, "missing-code-license-pin"), encoding="utf-8")
        require_rejected(root, "RESEARCH_EVIDENCE_DRIFT")
        checks += 1

    proc = run_verifier(REPO_ROOT)
    assert proc.returncode == 0, (proc.returncode, proc.stdout, proc.stderr)
    checks += 1
    print(f"THIRD PARTY PROVENANCE TEST PASS {checks}/8")


if __name__ == "__main__":
    run()
