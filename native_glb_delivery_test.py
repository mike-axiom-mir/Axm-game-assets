#!/usr/bin/env python3
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from native_geometry import make_box, write_obj
from native_glb_delivery import GlbDeliveryError, _parse_glb, build_verified_glb_delivery
from native_pipeline import build_rigid_package


def sha256_bytes(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def expect_rejected(fn, expected: str) -> None:
    try:
        fn()
    except GlbDeliveryError as exc:
        assert expected in str(exc), str(exc)
    else:
        raise AssertionError(f"expected GLB rejection containing {expected!r}")


def write_request(path: Path, *, asset_id: str, asset_type: str = "rigid-proxy", delivery=None) -> dict:
    request = {
        "contract": "axm.rts.forge-unit-request/v0.1",
        "asset": {"id": asset_id, "name": "Guard proxy", "type": asset_type, "unit_meters": 1.82},
        "targets": {"engines": ["threejs"], "delivery": delivery or ["glb"]},
        "budgets": {"triangles": {"lod0": 30000, "lod1": 15000, "lod2": 7000, "lod3": 3000}},
        "quality": {"pbr_channels": ["base_color", "normal", "roughness", "metallic"]},
        "variants": [{"id": "rts", "changes": ["proxy test"]}],
        "sources": [{"kind": "axm-unit-pack-source", "repository": "mike-axiom-mir/axm-many-race-rts-current", "ref": "0" * 40, "path": "src/contentPacks.js", "pack_id": "unit-pack:northpole:core", "pack_source": "builtin-faction", "faction_id": "northpole", "unit_id": "guard"}],
    }
    path.write_text(json.dumps(request, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return request


def run() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        asset_id = "rts-northpole-guard"
        source = root / "guard-proxy.obj"
        write_obj(make_box((0.65, 1.82, 0.42), name=asset_id), source, include_normals=False)
        package_dir = root / "package"
        package = build_rigid_package(source, package_dir, material_size=32, seed=20260910)
        pin = package["manifest_sha256"]
        request_path = root / "request.json"
        request = write_request(request_path, asset_id=asset_id)

        package_before = {p.relative_to(package_dir).as_posix(): p.read_bytes() for p in package_dir.rglob("*") if p.is_file()}
        first_path = root / "first.glb"
        second_path = root / "second.glb"
        first = build_verified_glb_delivery(package_dir, first_path, expected_manifest_sha256=pin, consumer_request=request_path)
        second = build_verified_glb_delivery(package_dir, second_path, expected_manifest_sha256=pin, consumer_request=request_path)
        assert first["schema"] == "axm.game-assets.verified-glb-delivery/v0.1"
        assert first["status"] == "READY_FOR_EXPLICIT_CONSUMER_LOAD"
        assert first["consumer_request"]["contract"] == request["contract"]
        canonical = json.dumps(request, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        assert first["consumer_request"]["sha256"] == sha256_bytes(canonical)
        assert first["delivery"]["self_contained"] is True
        assert first["delivery"]["validation"]["images_embedded"] == 3
        assert first["delivery"]["sha256"] == second["delivery"]["sha256"]
        assert first_path.read_bytes() == second_path.read_bytes()
        assert first["authority"] == {
            "canonical_genome_mutation": False,
            "source_package_mutation": False,
            "automatic_consumer_install": False,
            "automatic_runtime_adoption": False,
            "visual_approval": False,
            "merge": False,
            "canon": False,
        }
        package_after = {p.relative_to(package_dir).as_posix(): p.read_bytes() for p in package_dir.rglob("*") if p.is_file()}
        assert package_after == package_before

        doc, embedded = _parse_glb(first_path.read_bytes())
        assert doc["asset"]["version"] == "2.0"
        assert doc["asset"]["extras"]["axm_verified_delivery"]["source_manifest_sha256"] == pin
        assert doc["buffers"] == [{"byteLength": len(embedded)}]
        assert all("uri" not in image and image["mimeType"] == "image/png" for image in doc["images"])
        assert all(image["bufferView"] < len(doc["bufferViews"]) for image in doc["images"])

        bad_type = root / "bad-type.json"
        write_request(bad_type, asset_id=asset_id, asset_type="character")
        expect_rejected(
            lambda: build_verified_glb_delivery(package_dir, root / "bad-type.glb", expected_manifest_sha256=pin, consumer_request=bad_type),
            "only explicit rigid-proxy",
        )
        assert not (root / "bad-type.glb").exists()

        bad_target = root / "bad-target.json"
        write_request(bad_target, asset_id=asset_id, delivery=["gltf"])
        expect_rejected(
            lambda: build_verified_glb_delivery(package_dir, root / "bad-target.glb", expected_manifest_sha256=pin, consumer_request=bad_target),
            "threejs + glb",
        )

        wrong_asset = root / "wrong-asset.json"
        write_request(wrong_asset, asset_id="another-asset")
        expect_rejected(
            lambda: build_verified_glb_delivery(package_dir, root / "wrong.glb", expected_manifest_sha256=pin, consumer_request=wrong_asset),
            "asset identity",
        )

        expect_rejected(
            lambda: build_verified_glb_delivery(package_dir, root / "wrong-pin.glb", expected_manifest_sha256="sha256:" + "0" * 64),
            "source package verification failed",
        )

        binary_path = package_dir / package["delivery"]["binary"]
        binary_path.write_bytes(binary_path.read_bytes() + b"tamper")
        expect_rejected(
            lambda: build_verified_glb_delivery(package_dir, root / "tampered.glb", expected_manifest_sha256=pin),
            "source package verification failed",
        )
        assert not (root / "tampered.glb").exists()
        print("VERIFIED GLB DELIVERY TEST PASS", first["delivery"]["bytes"], "bytes")


if __name__ == "__main__":
    run()
