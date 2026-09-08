#!/usr/bin/env python3
from native_hm08_landmarks import load_preferred_hm08_landmarks


def run() -> None:
    first = load_preferred_hm08_landmarks()
    second = load_preferred_hm08_landmarks()
    assert first == second

    eye_y = (first.left_eye[1] + first.right_eye[1]) * 0.5
    nose_y = first.nose_tip[1]
    mouth_y = first.mouth_center[1]
    chin_y = first.chin_center[1]
    eye_to_nose = eye_y - nose_y
    nose_to_mouth = nose_y - mouth_y

    assert eye_y > nose_y > mouth_y > chin_y, (eye_y, nose_y, mouth_y, chin_y)
    assert 0.20 < eye_to_nose < 0.60, eye_to_nose
    assert eye_to_nose * 0.45 < nose_to_mouth < eye_to_nose * 1.50, (eye_to_nose, nose_to_mouth)
    assert abs(first.mouth_center[0]) < 0.05, first.mouth_center
    assert first.mouth_center[2] < first.nose_tip[2], (first.mouth_center, first.nose_tip)
    assert first.mouth_center[2] > first.bounds_min[2] + (first.bounds_max[2] - first.bounds_min[2]) * 0.55
    assert first.evidence["mouth_search"]["candidate_count"] >= 12
    assert first.evidence["mouth_search"]["forward_candidate_count"] >= 4
    assert first.evidence["truth"]["crop_boundary_used"] is False
    assert first.evidence["truth"]["source_vertex_ids_required"] is False

    print(
        "HM08 LANDMARK TEST PASS",
        {"eye_y":eye_y,"nose":first.nose_tip,"mouth":first.mouth_center,"chin":first.chin_center,"nose_to_mouth":nose_to_mouth},
        first.evidence["mouth_search"],
    )


if __name__ == "__main__":
    run()
