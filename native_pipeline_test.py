#!/usr/bin/env python3
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

from native_geometry import make_box, write_obj
from native_pipeline import PackageVerificationError, build_rigid_package, verify_rigid_package
from native_uv import box_project, write_obj_uv


def expect_rejected(fn, expected: str) -> None:
    try:
        fn()
    except PackageVerificationError as exc:
        assert expected in str(exc), str(exc)
    else:
        raise AssertionError(f"expected package rejection containing {expected!r}")


def manifest_digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def run() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        no_uv = root / "input-no-uv.obj"
        mesh = make_box((0.8, 0.22, 1.1), name="sentinel_plate_route")
        write_obj(mesh, no_uv, include_normals=False)
        package = build_rigid_package(no_uv, root / "package-a", material_size=64, seed=31415)
        assert package["truth"]["blender_required"] is False
        assert package["truth"]["high_end_character_claim"] is False
        assert package["uv"]["decision"] == "box_projection_fallback"
        assert package["delivery"]["validation"]["status"] == "pass"
        assert (root / "package-a" / "package-manifest.json").exists()
        assert len(list((root / "package-a" / "receipts").glob("*.json"))) == 5
        verified = verify_rigid_package(
            root / "package-a",
            expected_manifest_sha256=package["manifest_sha256"],
        )
        assert verified["status"] == "pass"
        assert verified["files_verified"] == len(package["files"])
        assert verified["receipts_verified"] == 5
        command = subprocess.run(
            [
                sys.executable,
                str(Path(__file__).with_name("native_pipeline.py")),
                "--verify",
                str(root / "package-a"),
                "--expected-manifest-sha256",
                package["manifest_sha256"],
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        assert json.loads(command.stdout)["status"] == "pass"

        with_uv = root / "input-with-uv.obj"
        uv = box_project(mesh)
        write_obj_uv(mesh, uv, with_uv)
        preserved = build_rigid_package(with_uv, root / "package-b", material_size=64, seed=31415)
        assert preserved["uv"]["decision"] == "preserved"
        assert preserved["delivery"]["binary_sha256"] == package["delivery"]["binary_sha256"]

        artifact_package = root / "artifact-tamper"
        artifact = build_rigid_package(no_uv, artifact_package, material_size=8, seed=1)
        binary_path = next(path for path in artifact["files"] if path.endswith(".bin"))
        (artifact_package / binary_path).write_bytes(b"forged delivery")
        expect_rejected(
            lambda: verify_rigid_package(artifact_package, expected_manifest_sha256=artifact["manifest_sha256"]),
            "delivery digest mismatch",
        )

        receipt_package = root / "receipt-tamper"
        receipt_built = build_rigid_package(no_uv, receipt_package, material_size=8, seed=2)
        receipt_path = sorted((receipt_package / "receipts").glob("*.json"))[0]
        receipt = json.loads(receipt_path.read_text())
        receipt["status"] = "fail"
        receipt_path.write_text(json.dumps(receipt) + "\n")
        expect_rejected(
            lambda: verify_rigid_package(receipt_package, expected_manifest_sha256=receipt_built["manifest_sha256"]),
            "receipt digest mismatch",
        )

        extra_package = root / "undeclared-file"
        extra = build_rigid_package(no_uv, extra_package, material_size=8, seed=3)
        (extra_package / "unclaimed.bin").write_bytes(b"not in manifest")
        expect_rejected(
            lambda: verify_rigid_package(extra_package, expected_manifest_sha256=extra["manifest_sha256"]),
            "inventory mismatch",
        )

        resealed_package = root / "resealed-manifest"
        resealed = build_rigid_package(no_uv, resealed_package, material_size=8, seed=4)
        manifest_path = resealed_package / "package-manifest.json"
        manifest = json.loads(manifest_path.read_text())
        manifest["truth"]["high_end_character_claim"] = True
        manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
        assert manifest_digest(manifest_path) != resealed["manifest_sha256"]
        expect_rejected(
            lambda: verify_rigid_package(resealed_package, expected_manifest_sha256=resealed["manifest_sha256"]),
            "caller-owned digest",
        )

        symlink_package = root / "symlink-substitution"
        symlink_built = build_rigid_package(no_uv, symlink_package, material_size=8, seed=5)
        source_copy = symlink_package / "source" / no_uv.name
        outside = root / "outside.obj"
        outside.write_bytes(source_copy.read_bytes())
        source_copy.unlink()
        os.symlink(outside, source_copy)
        expect_rejected(
            lambda: verify_rigid_package(symlink_package, expected_manifest_sha256=symlink_built["manifest_sha256"]),
            "contains symlink",
        )
        print("NATIVE PIPELINE TEST PASS", package["delivery"]["gltf"], len(package["files"]), "hashed files")


if __name__ == "__main__":
    run()
