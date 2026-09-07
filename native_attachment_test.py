#!/usr/bin/env python3
from native_animation import AnimationClip, AnimationTrack
from native_attachment import Socket, TwoHandAttachment, contact_evidence, sample_two_hand_contact
from native_skin import Joint, Skeleton


def run() -> None:
    skeleton = Skeleton([
        Joint("root"),
        Joint("right_hand", parent=0, translation=(0.30, 1.0, 0.0)),
        Joint("left_hand", parent=0, translation=(-0.10, 1.0, 0.0)),
    ])
    attachment = TwoHandAttachment(
        primary_joint=1,
        support_joint=2,
        primary_socket=Socket("primary_grip", (0.0, 0.0, 0.0)),
        support_socket=Socket("support_grip", (-0.40, 0.0, 0.0)),
    )
    static = contact_evidence(skeleton, attachment)
    assert static["primary_position_error"] < 1e-10
    assert static["support_position_error"] < 1e-10
    assert static["support_orientation_error_deg"] < 1e-8

    carry = AnimationClip("carry", [
        AnimationTrack(0, "translation", [0.0, 1.0], [(0.0, 0.0, 0.0), (0.25, 0.10, -0.15)])
    ])
    carried = sample_two_hand_contact(skeleton, carry, attachment, [0.0, 0.25, 0.5, 0.75, 1.0])
    assert carried["max_primary_position_error"] < 1e-9
    assert carried["max_support_position_error"] < 1e-9

    broken = AnimationClip("support_slip", [
        AnimationTrack(2, "translation", [0.0, 1.0], [(-0.10, 1.0, 0.0), (-0.10, 1.12, 0.0)])
    ])
    slipped = sample_two_hand_contact(skeleton, broken, attachment, [0.0, 0.5, 1.0])
    assert slipped["max_primary_position_error"] < 1e-9
    assert slipped["max_support_position_error"] > 0.11
    print("NATIVE ATTACHMENT TEST PASS", carried["max_support_position_error"], "carry error", slipped["max_support_position_error"], "slip error")


if __name__ == "__main__":
    run()
