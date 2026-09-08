#!/usr/bin/env python3
from native_hm08_secondary_forms import build_preferred_secondary_form_candidate, displacement_report


def run() -> None:
    base, output, targets, landmarks, state = build_preferred_secondary_form_candidate()
    base2, output2, targets2, landmarks2, state2 = build_preferred_secondary_form_candidate()

    assert len(targets) == 12, sorted(targets)
    assert output.vertices == output2.vertices
    assert output.faces == base.faces == output2.faces
    assert landmarks == landmarks2
    assert state["target_state"] == state2["target_state"]
    assert set(targets) == set(targets2)
    assert all(len(target.deltas) > 0 for target in targets.values())

    paired = [
        ("left_brow_ridge", "right_brow_ridge"),
        ("left_upper_lid_form", "right_upper_lid_form"),
        ("left_lower_lid_trough", "right_lower_lid_trough"),
        ("left_cheek_plane", "right_cheek_plane"),
        ("left_nasolabial_crease", "right_nasolabial_crease"),
    ]
    for left, right in paired:
        a, b = len(targets[left].deltas), len(targets[right].deltas)
        assert abs(a - b) <= max(3, round(max(a, b) * 0.08)), (left, a, right, b)

    report = displacement_report(base, output)
    assert report["moved_vertices"] > 100, report
    assert report["mean_moved_distance_raw"] > 0.0, report
    assert report["max_distance_mm"] < 4.0, report

    eye_y = (landmarks.left_eye[1] + landmarks.right_eye[1]) * 0.5
    assert eye_y > landmarks.nose_tip[1] > landmarks.mouth_center[1] > landmarks.chin_center[1]

    print(
        "HM08 SECONDARY FORMS TEST PASS",
        report,
        {name: len(target.deltas) for name, target in sorted(targets.items())},
        {"mouth": landmarks.mouth_center, "chin": landmarks.chin_center},
    )


if __name__ == "__main__":
    run()
