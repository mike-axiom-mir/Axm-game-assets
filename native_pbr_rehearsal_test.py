#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from native_pbr import PaintedMetalSpec, write_painted_metal
from native_pbr_rehearsal import (
    NativePbrRehearsalError,
    normalize_policy,
    rehearse_native_pbr,
)
from native_pbr_signal_review import review_native_pbr


def _sha(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _normal_warnings(review: dict) -> set[str]:
    for row in review["audit"]["entries"]:
        if row["id"] == "normal":
            return set(row.get("warnings", []))
    raise AssertionError("normal row missing")


def run() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)

        source = root / "source-flat-normal"
        write_painted_metal(
            source,
            size=48,
            seed=404,
            spec=PaintedMetalSpec(normal_strength=0.0),
        )
        source_manifest = source / "material.json"
        source_manifest_hash = _sha(source_manifest)
        source_normal_hash = _sha(source / "normal.png")
        source_height_hash = _sha(source / "height.png")
        before = review_native_pbr(source_manifest)
        assert "near-flat-signal" in _normal_warnings(before), before

        receipt = rehearse_native_pbr(source_manifest, root / "rehearsal")
        assert receipt["schema"] == "axm.game-assets.native-pbr-rehearsal/v0.1"
        assert receipt["accepted_delta_count"] >= 1, receipt
        assert receipt["final_spec"]["normal_strength"] > 0.0
        assert receipt["source_manifest_unchanged"] is True
        assert receipt["authority"]["source_mutation"] is False
        assert receipt["authority"]["genome_mutation"] is False
        assert receipt["authority"]["canon"] is False
        assert _sha(source_manifest) == source_manifest_hash
        assert _sha(source / "normal.png") == source_normal_hash
        assert _sha(source / "height.png") == source_height_hash

        accepted = [item for item in receipt["attempts"] if item.get("accepted")]
        assert accepted, receipt
        first = accepted[0]
        assert first["comparison"]["target_warning_count_after"] < first["comparison"]["target_warning_count_before"]
        assert first["comparison"]["protected_map_hashes_unchanged"] is True
        assert first["comparison"]["normal_map_changed"] is True

        final_manifest = root / "rehearsal" / receipt["final_manifest_path"]
        after = review_native_pbr(final_manifest)
        assert len(_normal_warnings(after)) < len(_normal_warnings(before))
        assert after["status"] != "HOLD"

        healthy = root / "healthy"
        write_painted_metal(healthy, size=32, seed=405)
        healthy_review = review_native_pbr(healthy / "material.json")
        healthy_receipt = rehearse_native_pbr(
            healthy / "material.json",
            root / "healthy-rehearsal",
        )
        assert healthy_receipt["accepted_delta_count"] == 0
        assert healthy_receipt["stop_reason"] == "NO_JUSTIFIED_AUTO_DELTA"
        assert healthy_receipt["final_review_digest"] == healthy_review["review_digest"]

        try:
            rehearse_native_pbr(
                healthy / "material.json",
                root / "healthy-rehearsal",
            )
        except NativePbrRehearsalError as exc:
            assert "already exists" in str(exc)
        else:
            raise AssertionError("expected create-only rehearsal output rejection")

        malformed = root / "malformed"
        write_painted_metal(malformed, size=16, seed=406)
        manifest_path = malformed / "material.json"
        manifest = json.loads(manifest_path.read_text())
        manifest["size"] = [16, 8]
        manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
        try:
            rehearse_native_pbr(manifest_path, root / "malformed-rehearsal")
        except NativePbrRehearsalError as exc:
            assert "square" in str(exc)
        else:
            raise AssertionError("expected non-square source rejection")

        policy = normalize_policy(
            {
                "max_passes": 3,
                "min_normal_strength": 0.2,
                "max_normal_strength": 4.0,
                "near_flat_bootstrap_strength": 0.8,
                "weak_z_scale": 0.5,
            }
        )
        assert policy["max_passes"] == 3
        assert policy["policy_digest"].startswith("sha256:")
        try:
            normalize_policy({"unknown": 1})
        except NativePbrRehearsalError as exc:
            assert "unknown rehearsal policy" in str(exc)
        else:
            raise AssertionError("expected unknown policy rejection")

        print(
            "NATIVE PBR REHEARSAL TEST PASS",
            receipt["accepted_delta_count"],
            "accepted technical repair(s)",
        )


if __name__ == "__main__":
    run()
