#!/usr/bin/env python3
from pathlib import Path
from tempfile import TemporaryDirectory

from native_hm08_skin_bake import write_hm08_semantic_skin


def run() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        first = write_hm08_semantic_skin(root / "a", size=32, seed=20801)
        second = write_hm08_semantic_skin(root / "b", size=32, seed=20801)
        changed = write_hm08_semantic_skin(root / "c", size=32, seed=20802)

        assert first["truth"]["deterministic"] is True
        assert first["truth"]["human_scan"] is False
        assert first["evidence"]["coverage"] > 0.10, first["evidence"]
        assert first["evidence"]["semantic_fraction_of_covered"] > 0.05, first["evidence"]
        assert first["evidence"]["landmarks"]["mouth_boundary_vertices"] == 12, first["evidence"]
        assert all(value > 0.20 for value in first["evidence"]["region_max"].values()), first["evidence"]["region_max"]
        assert "region_debug" in first["maps"]
        assert first["maps"]["orm"]["channels"] == 3

        first_hashes = {name: item["sha256"] for name, item in first["maps"].items()}
        second_hashes = {name: item["sha256"] for name, item in second["maps"].items()}
        changed_hashes = {name: item["sha256"] for name, item in changed["maps"].items()}
        assert first_hashes == second_hashes
        assert first_hashes != changed_hashes
        assert first["maps"]["base_color"]["sha256"] != first["maps"]["region_debug"]["sha256"]

        print(
            "HM08 SEMANTIC SKIN TEST PASS",
            first["evidence"]["coverage"],
            first["evidence"]["semantic_fraction_of_covered"],
            first["evidence"]["region_max"],
        )


if __name__ == "__main__":
    run()
