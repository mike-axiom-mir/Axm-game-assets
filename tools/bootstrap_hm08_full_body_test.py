#!/usr/bin/env python3
from argparse import Namespace
from pathlib import Path
from tempfile import TemporaryDirectory
import json

from bootstrap_hm08_full_body import build


def write_fixture(root: Path):
    vertices = []
    for y in (0.0, 4.0, 8.0, 12.0):
        vertices.extend([(-2,y,-1),(2,y,-1),(2,y,1),(-2,y,1)])
    # Four helper vertices outside the declared body range.
    vertices.extend([(-1,20,-1),(1,20,-1),(1,20,1),(-1,20,1)])
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
    faces.extend([(0,3,2,1),(12,13,14,15),(16,17,18,19)])
    lines = ["# synthetic hm08 full body fixture"]
    for vertex in vertices:
        lines.append("v %s %s %s" % vertex)
    for index in range(len(vertices)):
        lines.append(f"vt {(index % 4)/3:.6f} {(index // 4)/5:.6f}")
    for face in faces:
        lines.append("f " + " ".join(f"{i+1}/{i+1}" for i in face))
    base = root / "base.obj"
    base.write_text("\n".join(lines) + "\n", encoding="utf-8")

    config = {"groups_by_range": {"body":[0,15]}}
    config_path = root / "hm08_config.json"
    config_path.write_text(json.dumps(config), encoding="utf-8")

    target = root / "face.target"
    target.write_text("# synthetic\n0 0.01 0 0\n10 0.1 0 0\n18 99 99 99\n", encoding="utf-8")
    head_map = root / "head-map.json"
    head_map.write_text(json.dumps({"compact_to_source":list(range(8,16))}), encoding="utf-8")
    upper_map = root / "upper-map.json"
    upper_map.write_text(json.dumps({"compact_to_source":list(range(4,16))}), encoding="utf-8")
    return base, config_path, target, head_map, upper_map


def run() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        base, config, target, head_map, upper_map = write_fixture(root)
        output = root / "out"
        result = build(Namespace(
            base_obj=str(base),
            config_json=str(config),
            target=[str(target)],
            required_head_source_map=str(head_map),
            required_upper_source_map=str(upper_map),
            output=str(output),
            makehuman_revision="synthetic",
            mpfb_revision="synthetic",
            minimum_faces=4,
            real_threshold=4,
        ))
        assert all(result["acceptance"].values()), result
        extraction = result["extraction"]
        assert extraction["selection_method"] == "declared_hm08_body_range_then_largest_connected_surface"
        assert extraction["declared_body_range"] == [0,15]
        assert extraction["compact_vertices"] == 16
        assert extraction["compact_faces"] == 14
        rel = result["relationship_to_promoted_substrates"]
        assert rel["head_source_subset"] is True
        assert rel["upper_body_source_subset"] is True
        mapping = json.loads((output / "source-index-map.json").read_text())
        assert mapping["compact_to_source"] == list(range(16))
        target_text = (output / "targets" / "face.target").read_text()
        assert "# basemesh axm-hm08-full-body-v0.1" in target_text
        assert "0 0.01 0 0" in target_text
        assert "10 0.1 0 0" in target_text
        assert "99 99 99" not in target_text
        print("HM08 FULL BODY UNIT PASS", extraction)


if __name__ == "__main__":
    run()
