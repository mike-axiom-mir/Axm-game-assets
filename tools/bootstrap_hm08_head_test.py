#!/usr/bin/env python3
from argparse import Namespace
from pathlib import Path
from tempfile import TemporaryDirectory
import json

from bootstrap_hm08_head import build


def write_fixture(root: Path) -> tuple[Path, Path, list[Path]]:
    # Two disconnected cubes: source vertices 0..7 are the synthetic head,
    # 8..15 are body noise outside the head metadata bounds. Each face carries
    # source UVs so the bootstrap must preserve v/vt pairing.
    vertices = [
        (-1,-1,-1),(1,-1,-1),(1,1,-1),(-1,1,-1),
        (-1,-1,1),(1,-1,1),(1,1,1),(-1,1,1),
        (-3,-3,-5),(3,-3,-5),(3,3,-5),(-3,3,-5),
        (-3,-3,-3),(3,-3,-3),(3,3,-3),(-3,3,-3),
    ]
    faces = [
        (0,3,2,1),(4,5,6,7),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7),
        (8,11,10,9),(12,13,14,15),(8,9,13,12),(9,10,14,13),(10,11,15,14),(11,8,12,15),
    ]
    lines = ["# synthetic hm08-like fixture"]
    for v in vertices:
        lines.append("v %s %s %s" % v)
    for i in range(len(vertices)):
        lines.append(f"vt {(i % 4)/3:.6f} {(i // 4)/3:.6f}")
    for face in faces:
        lines.append("f " + " ".join(f"{i+1}/{i+1}" for i in face))
    base = root / "base.obj"
    base.write_text("\n".join(lines) + "\n", encoding="utf-8")

    # Extrema indices point at the head cube vertices.
    config = {
        "dimensions": {"Head": {"xmin":0,"xmax":1,"ymin":0,"ymax":2,"zmin":0,"zmax":4}},
        "groups_by_range": {"body":[0,15]},
    }
    config_path = root / "hm08_config.json"
    config_path.write_text(json.dumps(config), encoding="utf-8")

    target = root / "nose-width.target"
    target.write_text(
        "# CC0 synthetic target\n# basemesh hm08\n0 0.1 0 0\n1 -0.1 0 0\n10 99 99 99\n",
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
        assert result["extraction"]["compact_vertices"] == 8
        assert result["extraction"]["compact_faces"] == 6
        assert result["extraction"]["compact_uvs"] == 8
        mapping = json.loads((output / "source-index-map.json").read_text())
        assert mapping["compact_to_source"] == list(range(8))
        remapped = (output / "targets" / "nose-width.target").read_text()
        assert "0 0.1 0 0" in remapped
        assert "1 -0.1 0 0" in remapped
        assert "99 99 99" not in remapped
        assert "vt " in (output / "head.obj").read_text()
        print("HM08 HEAD BOOTSTRAP UNIT PASS", result["extraction"])


if __name__ == "__main__":
    run()
