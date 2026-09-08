#!/usr/bin/env python3
from argparse import Namespace
from pathlib import Path
from tempfile import TemporaryDirectory
import json

from bootstrap_hm08_upper_body import build


def write_fixture(root: Path):
    # Four connected square rings in raw MakeHuman Y. The extraction should keep
    # the torso-to-head slab (Y 4..12) as one continuous surface and drop only
    # the lower segment below Y=4.
    vertices = []
    for y in (0.0, 4.0, 8.0, 12.0):
        vertices.extend([(-2,y,-1),(2,y,-1),(2,y,1),(-2,y,1)])
    faces = []
    for ring in range(3):
        a = ring * 4
        b = (ring + 1) * 4
        faces.extend([
            (a+0,a+1,b+1,b+0),
            (a+1,a+2,b+2,b+1),
            (a+2,a+3,b+3,b+2),
            (a+3,a+0,b+0,b+3),
        ])
    faces.append((12,13,14,15))
    lines = ["# synthetic hm08 upper body fixture"]
    for vertex in vertices:
        lines.append("v %s %s %s" % vertex)
    for index in range(len(vertices)):
        lines.append(f"vt {(index % 4)/3:.6f} {(index // 4)/3:.6f}")
    for face in faces:
        lines.append("f " + " ".join(f"{i+1}/{i+1}" for i in face))
    base = root / "base.obj"
    base.write_text("\n".join(lines) + "\n", encoding="utf-8")

    # MPFB raw-Y bounds are read from zmin/zmax because Blender Z=raw Y.
    config = {
        "dimensions": {
            "Head": {"xmin":12,"xmax":13,"ymin":12,"ymax":13,"zmin":8,"zmax":12},
            "Torso": {"xmin":4,"xmax":5,"ymin":4,"ymax":5,"zmin":4,"zmax":8},
        },
        "groups_by_range": {"body":[0,15]},
    }
    config_path = root / "hm08_config.json"
    config_path.write_text(json.dumps(config), encoding="utf-8")

    target = root / "face.target"
    target.write_text("# synthetic\n8 0.1 0 0\n12 -0.1 0 0\n0 99 99 99\n", encoding="utf-8")
    head_map = root / "head-map.json"
    head_map.write_text(json.dumps({"compact_to_source":[8,9,10,11,12,13,14,15]}), encoding="utf-8")
    return base, config_path, target, head_map


def run() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        base, config, target, head_map = write_fixture(root)
        output = root / "out"
        result = build(Namespace(
            base_obj=str(base),
            config_json=str(config),
            target=[str(target)],
            required_head_source_map=str(head_map),
            output=str(output),
            makehuman_revision="synthetic",
            mpfb_revision="synthetic",
            minimum_faces=4,
            real_threshold=4,
        ))
        assert all(result["acceptance"].values()), result
        extraction = result["extraction"]
        assert extraction["selection_method"] == "torso_to_head_vertical_slab_then_largest_connected_body_surface"
        assert extraction["vertical_slab_y"] == [4.0, 12.0]
        assert extraction["compact_vertices"] == 12
        assert extraction["compact_faces"] == 9
        assert result["relationship_to_head_seed"]["head_source_subset"] is True
        assert result["relationship_to_head_seed"]["missing_head_source_vertices"] == []
        mapping = json.loads((output / "source-index-map.json").read_text())
        assert mapping["compact_to_source"] == list(range(4,16))
        target_text = (output / "targets" / "face.target").read_text()
        assert "# basemesh axm-hm08-upper-body-v0.1" in target_text
        assert "4 0.1 0 0" in target_text
        assert "8 -0.1 0 0" in target_text
        assert "99 99 99" not in target_text
        print("HM08 UPPER BODY UNIT PASS", extraction)


if __name__ == "__main__":
    run()
