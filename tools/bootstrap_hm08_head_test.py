#!/usr/bin/env python3
from argparse import Namespace
from pathlib import Path
from tempfile import TemporaryDirectory
import json

from bootstrap_hm08_head import build


def write_fixture(root: Path) -> tuple[Path, Path, list[Path]]:
    # Two disconnected boxes. The synthetic head uses deliberately asymmetric
    # raw MakeHuman Y/Z ranges so a mistaken Blender-axis interpretation cannot
    # accidentally pass:
    #   raw X = [-1, 1]
    #   raw Y = [10, 12]
    #   raw Z = [-4, -2]
    # In Blender-space metadata this means:
    #   X extrema use raw X
    #   Y extrema use -raw Z
    #   Z extrema use raw Y
    vertices = [
        (-1,10,-4),(1,10,-4),(1,12,-4),(-1,12,-4),
        (-1,10,-2),(1,10,-2),(1,12,-2),(-1,12,-2),
        (-3,0,-9),(3,0,-9),(3,4,-9),(-3,4,-9),
        (-3,0,-7),(3,0,-7),(3,4,-7),(-3,4,-7),
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

    # MPFB extrema names are Blender axes. For the raw head above:
    # Blender X min/max -> source 0/1
    # Blender Y min/max (-raw Z) -> source 4/0
    # Blender Z min/max ( raw Y) -> source 0/2
    config = {
        "dimensions": {"Head": {"xmin":0,"xmax":1,"ymin":4,"ymax":0,"zmin":0,"zmax":2}},
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
        bounds = result["extraction"]["head_bounds"]
        assert bounds["x"] == [-1.0, 1.0]
        assert bounds["y"] == [10.0, 12.0]
        assert bounds["z"] == [-4.0, -2.0]
        assert bounds["mpfb_to_raw_axis_mapping"]["raw_y"] == ["zmin", "zmax"]
        assert bounds["mpfb_to_raw_axis_mapping"]["raw_z"] == ["ymin", "ymax"]
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
