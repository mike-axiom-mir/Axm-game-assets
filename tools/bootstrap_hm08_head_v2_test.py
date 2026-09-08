#!/usr/bin/env python3
from argparse import Namespace
from pathlib import Path
from tempfile import TemporaryDirectory
import json

from bootstrap_hm08_head_v2 import build


def write_fixture(root: Path):
    # Connected synthetic head where lower vertices protrude beyond the MPFB
    # X scale landmarks. v0.1-style 3D cropping would lose those vertices/faces.
    # v0.2 must keep them because they are inside the metadata-derived raw-Y
    # head slab and part of the largest connected body surface.
    vertices = [
        (-2,10,-4),(2,10,-4),(2,12,-4),(-2,12,-4),
        (-1,10,-2),(1,10,-2),(1,12,-2),(-1,12,-2),
        (-3,0,-9),(3,0,-9),(3,4,-9),(-3,4,-9),
        (-3,0,-7),(3,0,-7),(3,4,-7),(-3,4,-7),
    ]
    faces = [
        (0,3,2,1),(4,5,6,7),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7),
        (8,11,10,9),(12,13,14,15),(8,9,13,12),(9,10,14,13),(10,11,15,14),(11,8,12,15),
    ]
    lines = ["# synthetic hm08 v0.2 fixture"]
    for vertex in vertices:
        lines.append("v %s %s %s" % vertex)
    for index in range(len(vertices)):
        lines.append(f"vt {(index % 4)/3:.6f} {(index // 4)/3:.6f}")
    for face in faces:
        lines.append("f " + " ".join(f"{i+1}/{i+1}" for i in face))
    base = root / "base.obj"
    base.write_text("\n".join(lines) + "\n", encoding="utf-8")

    # Blender-axis MPFB labels. X landmarks intentionally reference the narrower
    # top/back vertices (-1,+1) instead of the full synthetic head extent (-2,+2).
    config = {
        "dimensions": {"Head": {"xmin":4,"xmax":5,"ymin":4,"ymax":0,"zmin":0,"zmax":2}},
        "groups_by_range": {"body":[0,15]},
    }
    config_path = root / "hm08_config.json"
    config_path.write_text(json.dumps(config), encoding="utf-8")

    target = root / "nose-width.target"
    target.write_text(
        "# synthetic CC0-like target\n# basemesh hm08\n0 0.1 0 0\n1 -0.1 0 0\n10 99 99 99\n",
        encoding="utf-8",
    )
    return base, config_path, [target]


def run() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        base, config, targets = write_fixture(root)
        output = root / "out"
        result = build(Namespace(
            base_obj=str(base),
            config_json=str(config),
            target=[str(path) for path in targets],
            output=str(output),
            makehuman_revision="synthetic",
            mpfb_revision="synthetic",
            minimum_faces=4,
            real_threshold=4,
        ))
        assert all(result["acceptance"].values()), result
        extraction = result["extraction"]
        assert extraction["selection_method"] == "metadata_vertical_slab_then_largest_connected_body_surface"
        assert extraction["compact_vertices"] == 8
        assert extraction["compact_faces"] == 6
        assert extraction["compact_uvs"] == 8
        assert extraction["metadata_reference_bounds"]["x"] == [-1.0, 1.0]
        assert extraction["compact_actual_bounds"]["x"] == [-2.0, 2.0]
        assert extraction["vertical_slab_y"] == [10.0, 12.0]
        mapping = json.loads((output / "source-index-map.json").read_text())
        assert mapping["compact_to_source"] == list(range(8))
        target_text = (output / "targets" / "nose-width.target").read_text()
        assert "# basemesh axm-hm08-head-v0.2" in target_text
        assert "0 0.1 0 0" in target_text and "1 -0.1 0 0" in target_text
        assert "99 99 99" not in target_text
        print("HM08 HEAD V0.2 UNIT PASS", extraction)


if __name__ == "__main__":
    run()
