#!/usr/bin/env python3
from pathlib import Path
from tempfile import TemporaryDirectory

from native_pbr import write_painted_metal


def run() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        a = write_painted_metal(root / "a", size=64, seed=77)
        b = write_painted_metal(root / "b", size=64, seed=77)
        c = write_painted_metal(root / "c", size=64, seed=78)
        assert set(a["maps"]) == {"base_color", "roughness", "metallic", "height", "normal", "ao"}
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
        print("NATIVE PBR TEST PASS", len(hashes_a), "maps")


if __name__ == "__main__":
    run()
