#!/usr/bin/env python3
from pathlib import Path
from tempfile import TemporaryDirectory

from native_pbr import PaintedMetalSpec, painted_metal_fields, write_painted_metal


def _normal_xy_energy(normal_bytes: bytes) -> float:
    samples = len(normal_bytes) // 3
    total = 0.0
    for index in range(samples):
        nx = normal_bytes[index * 3] / 255.0 * 2.0 - 1.0
        ny = normal_bytes[index * 3 + 1] / 255.0 * 2.0 - 1.0
        total += abs(nx) + abs(ny)
    return total / max(samples, 1)


def run() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        a = write_painted_metal(root / "a", size=64, seed=77)
        b = write_painted_metal(root / "b", size=64, seed=77)
        c = write_painted_metal(root / "c", size=64, seed=78)
        assert set(a["maps"]) == {"base_color", "roughness", "metallic", "height", "normal", "ao", "orm"}
        hashes_a = {k: v["sha256"] for k, v in a["maps"].items()}
        hashes_b = {k: v["sha256"] for k, v in b["maps"].items()}
        hashes_c = {k: v["sha256"] for k, v in c["maps"].items()}
        assert hashes_a == hashes_b
        assert hashes_a != hashes_c
        for name in a["maps"]:
            data = (root / "a" / f"{name}.png").read_bytes()
            assert data.startswith(b"\x89PNG\r\n\x1a\n")
        assert a["truth"]["physically_measured"] is False
        assert a["truth"]["deterministic"] is True
        assert a["maps"]["orm"]["channels"] == 3
        assert a["schema"] == "axm.game-assets.native-pbr.v0.2"
        assert a["spec"]["normal_strength"] == 4.0
        assert a["spec"]["height_grain_amplitude"] == 0.11

        restrained = PaintedMetalSpec(
            height_grain_amplitude=0.014,
            height_broad_amplitude=0.006,
            height_scratch_depth=0.025,
            height_pit_depth=0.002,
            pit_wear_strength=0.04,
            base_grain_variation=0.035,
            roughness_grain_variation=0.025,
            normal_strength=1.15,
        )
        default_fields = painted_metal_fields(64, 501)
        restrained_fields = painted_metal_fields(64, 501, restrained)
        default_energy = _normal_xy_energy(default_fields["normal"][1])
        restrained_energy = _normal_xy_energy(restrained_fields["normal"][1])
        assert restrained_energy < default_energy * 0.45, (default_energy, restrained_energy)

        restrained_manifest = write_painted_metal(root / "restrained", size=32, seed=501, spec=restrained)
        assert restrained_manifest["spec"]["normal_strength"] == 1.15
        assert restrained_manifest["spec"]["height_pit_depth"] == 0.002
        print(
            "NATIVE PBR TEST PASS",
            len(hashes_a),
            "maps",
            "normal energy",
            round(default_energy, 6),
            "->",
            round(restrained_energy, 6),
        )


if __name__ == "__main__":
    run()
