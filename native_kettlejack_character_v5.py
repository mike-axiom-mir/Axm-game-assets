#!/usr/bin/env python3
"""Kettlejack v0.5 recovery of the v0.4 visual repair pass.

v0.4 correctly failed before rendering because the proposed smile-teeth plate
asked the shared rounded-box organ for an invalid chamfer relative to its tiny
height. That failed state is retained. v0.5 keeps the same render-driven design
changes, but clamps caller-authored chamfers to the construction organ's valid
geometric range instead of weakening that organ's validation.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import native_kettlejack_character_v4 as v4
from native_construction_kit import rounded_box as _strict_rounded_box

SCHEMA = "axm.game-assets.kettlejack-character/v0.5"
ASSET_NAME = "kettlejack_game_character_v0_5"


def _sha(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _bounded_rounded_box(center, size, *, chamfer, name="rounded-box"):
    if len(size) != 3:
        return _strict_rounded_box(center, size, chamfer=chamfer, name=name)
    maximum = min(float(size[0]), float(size[1])) * 0.45
    return _strict_rounded_box(center, size, chamfer=min(float(chamfer), maximum), name=name)


def write_kettlejack_v5_package(output: str | Path, *, texture_size: int = 64, target_height_m: float = 1.30) -> dict[str, Any]:
    # Patch only the v0.4 caller surface. The shared construction kit remains
    # strict and unchanged; this is an explicit repair of our invalid request.
    old_box = v4.rounded_box
    old_schema = v4.SCHEMA
    old_name = v4.ASSET_NAME
    v4.rounded_box = _bounded_rounded_box
    v4.SCHEMA = SCHEMA
    v4.ASSET_NAME = ASSET_NAME
    try:
        package = v4.write_kettlejack_v4_package(output, texture_size=texture_size, target_height_m=target_height_m)
    finally:
        v4.rounded_box = old_box
        v4.SCHEMA = old_schema
        v4.ASSET_NAME = old_name

    root = Path(output)
    old_manifest = root / "kettlejack-v4-package.json"
    if old_manifest.exists():
        old_manifest.unlink()
    package["schema"] = SCHEMA
    package["candidate_role"] = "fourth_render_rehearsed_animated_game_character"
    package["recovery"] = {
        "from": "axm.game-assets.kettlejack-character/v0.4",
        "failure": "invalid caller chamfer on tiny smile-teeth rounded box",
        "repair": "bounded caller chamfer below half of smaller XY dimension; shared construction validator unchanged",
        "v0_4_failure_retained": True,
    }
    package["render_findings_addressed"] = list(package.get("render_findings_addressed", [])) + [
        "v0.4 structural test failure from invalid tiny-part chamfer"
    ]
    package["truth"]["visual_match_proven"] = False
    package["truth"]["render_review_required"] = True

    files = {}
    for path in sorted(root.rglob("*")):
        if path.is_file() and path.name != "kettlejack-v5-package.json":
            files[path.relative_to(root).as_posix()] = {"bytes": path.stat().st_size, "sha256": _sha(path.read_bytes())}
    package["files"] = files
    payload = (json.dumps(package, indent=2, sort_keys=True) + "\n").encode("utf-8")
    (root / "kettlejack-v5-package.json").write_bytes(payload)
    package["package_sha256"] = _sha(payload)
    return package


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("output")
    parser.add_argument("--texture-size", type=int, default=64)
    parser.add_argument("--height", type=float, default=1.30)
    args = parser.parse_args()
    package = write_kettlejack_v5_package(args.output, texture_size=args.texture_size, target_height_m=args.height)
    print(json.dumps({
        "schema": package["schema"],
        "height_m": package["height_m"],
        "triangles": package["delivery"]["triangles"],
        "primitives": package["delivery"]["primitive_count"],
        "animations": package["delivery"]["animations"],
        "acceptance": package["acceptance"],
        "recovery": package["recovery"],
        "package_sha256": package["package_sha256"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
