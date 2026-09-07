#!/usr/bin/env python3
from pathlib import Path
from tempfile import TemporaryDirectory

from native_geometry import Mesh, write_obj
from native_seed_bundle import build_seed_bundle


def run() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        seed = Mesh(
            "hm08-fixture",
            [(-1.0,0.0,0.0),(1.0,0.0,0.0),(-1.0,1.0,0.0),(1.0,1.0,0.0),(0.0,0.4,0.2),(0.0,0.7,0.15)],
            [(0,1,4),(1,3,5,4),(3,2,5),(2,0,4,5)],
        )
        base = root / "base.obj"
        write_obj(seed, base, include_normals=False)
        nose = root / "nose-width.target"
        nose.write_text("# basemesh hm08\n4 0 0 .08\n5 0 0 .04\n", encoding="utf-8")
        age = root / "older.target"
        age.write_text("# basemesh hm08\n0 .01 -.01 0\n2 .01 -.02 0\n", encoding="utf-8")

        out = root / "bundle"
        manifest = build_seed_bundle(
            base,
            [nose, age],
            {"nose-width": 0.5, "older": 0.25},
            out,
            seed_id="hm08-fixture",
            basemesh_id="hm08",
            seed_source="fixture://hm08",
            declared_license="CC0-1.0",
            license_evidence="fixture license evidence",
            unit_meters=0.1,
        )
        assert all(manifest["acceptance"].values())
        assert manifest["seed"]["basemesh_id"] == "hm08"
        assert len(manifest["targets"]) == 2
        assert (out / "seed.obj").exists()
        assert (out / "variant.obj").exists()
        assert (out / "parametric-state.json").exists()
        assert manifest["truth"]["license_verified_by_code"] is False

        wrong = root / "wrong.target"
        wrong.write_text("# basemesh othermesh\n4 0 0 .1\n", encoding="utf-8")
        try:
            build_seed_bundle(base, [wrong], {"wrong": 1.0}, root / "wrong-bundle", seed_id="hm08-fixture", basemesh_id="hm08")
        except ValueError:
            pass
        else:
            raise AssertionError("basemesh mismatch must fail")

        print("NATIVE SEED BUNDLE TEST PASS", manifest["parametric_state_digest"], manifest["outputs"])


if __name__ == "__main__":
    run()
