#!/usr/bin/env python3
from pathlib import Path
from tempfile import TemporaryDirectory
import json

from bootstrap_hm08_finger_landmarks import derive_finger_landmarks


def fixture(root: Path):
    vertices = []
    joints = {}
    bones = {}
    index = 0
    for side, sign in (("L", 1.0), ("R", -1.0)):
        for digit in range(1, 6):
            parent = "wrist.%s" % side
            base_x = sign * (1.0 + digit * 0.12)
            base_y = digit * 0.08
            for segment in range(1, 4):
                head_ref = f"finger{digit}-{segment}.{side}____head"
                tail_ref = f"finger{digit}-{segment}.{side}____tail"
                head = (base_x + sign * (segment - 1) * 0.08, base_y, segment * 0.025)
                tail = (base_x + sign * segment * 0.08, base_y + 0.006 * segment, segment * 0.027)
                vertices.extend([head, tail])
                joints[head_ref] = [index]
                joints[tail_ref] = [index + 1]
                bone_name = f"finger{digit}-{segment}.{side}"
                bones[bone_name] = {"head": head_ref, "tail": tail_ref, "parent": parent}
                parent = bone_name
                index += 2

    # parse_obj intentionally requires at least one face. The face is irrelevant
    # to landmark extraction but keeps the fixture faithful to a real OBJ.
    lines = ["# synthetic finger-landmark fixture"]
    for x, y, z in vertices:
        lines.append(f"v {x:.9g} {y:.9g} {z:.9g}")
    lines.append("f 1 2 3")
    base = root / "base.obj"
    base.write_text("\n".join(lines) + "\n", encoding="utf-8")
    rig = root / "default.mhskel"
    rig.write_text(json.dumps({"name": "synthetic", "bones": bones, "joints": joints}), encoding="utf-8")
    return base, rig


def run() -> None:
    with TemporaryDirectory() as td:
        root = Path(td)
        base, rig = fixture(root)
        first = derive_finger_landmarks(base, rig, makehuman_revision="synthetic")
        second = derive_finger_landmarks(base, rig, makehuman_revision="synthetic")
        assert first == second
        assert all(first["acceptance"].values()), first["acceptance"]
        assert first["finger_bone_count"] == 30
        assert first["side_counts"] == {"L": 15, "R": 15}
        assert first["digit_segments"] == {
            side: {str(digit): [1, 2, 3] for digit in range(1, 6)} for side in ("L", "R")
        }
        assert first["source_index_range"] == [0, 59]
        assert len(first["unique_joint_refs"]) == 60
        assert all(row["length_m"] > 0.0 for row in first["bones"])
        assert all(abs(row["head_m"][axis] - row["head_raw"][axis] * 0.1) < 1e-12 for row in first["bones"] for axis in range(3))
        assert first["truth"]["source_grounded"] is True
        assert first["truth"]["application_code_imported"] is False
        assert first["truth"]["production_finger_rig_claim"] is False

        # A source-index drift must hard-fail instead of silently moving a joint.
        bad = json.loads(rig.read_text())
        bad["joints"]["finger1-1.L____head"] = [9999]
        bad_path = root / "bad.mhskel"
        bad_path.write_text(json.dumps(bad), encoding="utf-8")
        try:
            derive_finger_landmarks(base, bad_path, makehuman_revision="synthetic")
        except ValueError as error:
            assert "outside base mesh" in str(error)
        else:
            raise AssertionError("invalid source joint index did not fail")

        print("HM08 FINGER LANDMARK BOOTSTRAP TEST PASS", {
            "bones": first["finger_bone_count"],
            "joint_refs": len(first["unique_joint_refs"]),
            "length_m_range": first["length_m_range"],
        })


if __name__ == "__main__":
    run()
