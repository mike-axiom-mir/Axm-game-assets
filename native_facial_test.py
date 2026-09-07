#!/usr/bin/env python3
from native_facial import (
    CorrectiveRule,
    DriverCondition,
    MorphWeightClip,
    evaluate_correctives,
    sample_morph_weight_clip,
    validate_morph_weight_clip,
)


def run() -> None:
    targets = ["blink_left", "blink_right", "smile", "cheek_corrective", "jaw_corrective"]
    rules = [
        CorrectiveRule(
            "smile_cheek",
            "cheek_corrective",
            (DriverCondition("smile", 0.25, 0.85), DriverCondition("cheek_raise", 0.15, 0.70)),
            gain=0.90,
            combine="product",
        ),
        CorrectiveRule(
            "jaw_fold",
            "jaw_corrective",
            (DriverCondition("jaw_open", 0.35, 0.90),),
            gain=0.75,
        ),
    ]
    driven = evaluate_correctives(
        {"smile": 0.85, "cheek_raise": 0.70, "jaw_open": 0.90},
        targets,
        rules,
        base_weights={"smile": 0.8},
    )
    assert abs(driven["weights"]["cheek_corrective"] - 0.90) < 1e-9
    assert abs(driven["weights"]["jaw_corrective"] - 0.75) < 1e-9
    assert driven["weights"]["smile"] == 0.8

    partial = evaluate_correctives(
        {"smile": 0.55, "cheek_raise": 0.425, "jaw_open": 0.35},
        targets,
        rules,
    )
    assert 0.15 < partial["weights"]["cheek_corrective"] < 0.35
    assert partial["weights"]["jaw_corrective"] == 0.0

    blink = MorphWeightClip(
        "blink",
        [0.0, 0.08, 0.16],
        [
            (0.0, 0.0, 0.0, 0.0, 0.0),
            (1.0, 1.0, 0.0, 0.0, 0.0),
            (0.0, 0.0, 0.0, 0.0, 0.0),
        ],
    )
    report = validate_morph_weight_clip(blink, len(targets))
    assert report["status"] == "pass", report
    half = sample_morph_weight_clip(blink, 0.04)
    assert abs(half[0] - 0.5) < 1e-9 and abs(half[1] - 0.5) < 1e-9
    assert sample_morph_weight_clip(blink, 0.08)[:2] == (1.0, 1.0)

    broken = MorphWeightClip("broken", [0.0, 0.1], [(0.0,), (1.2,)])
    assert validate_morph_weight_clip(broken, len(targets))["status"] == "fail"
    print("NATIVE FACIAL TEST PASS", driven["weights"], report)


if __name__ == "__main__":
    run()
