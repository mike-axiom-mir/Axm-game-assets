#!/usr/bin/env python3
from pathlib import Path
from tempfile import TemporaryDirectory

from native_hm08_skin_physical import write_hm08_physical_skin


def run() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        first = write_hm08_physical_skin(root / "a", size=64, seed=20801)
        second = write_hm08_physical_skin(root / "b", size=64, seed=20801)
        changed = write_hm08_physical_skin(root / "c", size=64, seed=20802)

        assert first["truth"]["deterministic"] is True
        assert first["truth"]["human_scan"] is False
        assert first["truth"]["noise_coordinate_space"].startswith("canonical 3D hm08")
        assert first["evidence"]["noise_space"] == "canonical_raw_hm08_decimeters"
        assert first["evidence"]["coverage"] > 0.10, first["evidence"]
        assert first["evidence"]["physical_scale_intent"]["pore"].startswith("0.5-1.5mm")
        assert all(value > 0.15 for value in first["evidence"]["region_max"].values()), first["evidence"]["region_max"]

        landmarks = first["evidence"]["landmarks"]
        eye_y = 7.28415
        assert eye_y > landmarks["nose_tip"][1] > landmarks["mouth_center"][1] > landmarks["chin_center"][1]
        assert 6.55 < landmarks["mouth_center"][1] < 6.75, landmarks["mouth_center"]

        first_hashes = {name:item["sha256"] for name,item in first["maps"].items()}
        second_hashes = {name:item["sha256"] for name,item in second["maps"].items()}
        changed_hashes = {name:item["sha256"] for name,item in changed["maps"].items()}
        assert first_hashes == second_hashes
        assert first_hashes != changed_hashes
        assert first["maps"]["orm"]["channels"] == 3
        assert first["maps"]["normal"]["channels"] == 3

        print(
            "HM08 PHYSICAL SKIN TEST PASS",
            first["evidence"]["coverage"],
            first["evidence"]["region_max"],
            landmarks,
        )


if __name__ == "__main__":
    run()
