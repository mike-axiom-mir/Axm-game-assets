#!/usr/bin/env python3
from native_animation import AnimationClip, AnimationTrack
from native_attachment import (
    Socket,
    TwoHandSocketAttachment,
    sample_two_hand_socket_contact,
    socket_contact_evidence,
)
from native_skin import Joint, Skeleton


def run() -> None:
    skeleton = Skeleton([
        Joint("root"),
        Joint("right_wrist", parent=0, translation=(0.25, 1.0, 0.0)),
        Joint("left_wrist", parent=0, translation=(-0.10, 1.0, 0.0)),
    ])
    attachment = TwoHandSocketAttachment(
        primary_joint=1,
        support_joint=2,
        primary_hand_socket=Socket("right_palm_grip", (0.05, 0.0, 0.0)),
        support_hand_socket=Socket("left_palm_grip", (-0.05, 0.0, 0.0)),
        primary_weapon_socket=Socket("primary_grip", (0.0, 0.0, 0.0)),
        support_weapon_socket=Socket("support_grip", (-0.45, 0.0, 0.0)),
    )
    static = socket_contact_evidence(skeleton, attachment)
    assert static["primary_position_error"] < 1e-10
    assert static["support_position_error"] < 1e-10
    assert static["primary_hand_contact_world_position"] == [0.3, 1.0, 0.0]
    assert static["support_hand_contact_world_position"] == [-0.15000000000000002, 1.0, 0.0]

    carry = AnimationClip("carry", [
        AnimationTrack(0, "translation", [0.0, 1.0], [(0.0, 0.0, 0.0), (0.20, 0.10, -0.10)])
    ])
    sampled = sample_two_hand_socket_contact(skeleton, carry, attachment, [0.0, 0.5, 1.0])
    assert sampled["max_primary_position_error"] < 1e-9
    assert sampled["max_support_position_error"] < 1e-9

    broken = AnimationClip("support_slip", [
        AnimationTrack(2, "translation", [0.0, 1.0], [(-0.10, 1.0, 0.0), (-0.10, 1.08, 0.0)])
    ])
    slipped = sample_two_hand_socket_contact(skeleton, broken, attachment, [0.0, 1.0])
    assert slipped["max_support_position_error"] > 0.079
    print("HAND SOCKET ATTACHMENT TEST PASS", {
        "static_support_error": static["support_position_error"],
        "carry_support_error": sampled["max_support_position_error"],
        "slip_support_error": slipped["max_support_position_error"],
    })


if __name__ == "__main__":
    run()
