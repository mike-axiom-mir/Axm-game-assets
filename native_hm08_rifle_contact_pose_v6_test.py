#!/usr/bin/env python3

from native_hm08_rifle_contact_pose_v6 import build_preferred_grip_volume_rifle_contact_pose


def run() -> None:
    try:
        build_preferred_grip_volume_rifle_contact_pose()
    except ValueError as exc:
        message = str(exc)
        assert "no collision-safe curl candidate for right digit 5" in message, message
        assert "0.010072609" in message or "0.010072" in message, message
        print("HM08 GRIP-VOLUME V0.6 EXPECTED REJECTION PASS", {
            "reason": "center-socket palm placement leaves no collision-safe right-pinky curl candidate",
            "minimum_observed_pinky_penetration_m_approx": 0.0100726,
            "truth": "v0.6 is retained as negative evidence; do not promote or weaken its collision boundary. v0.7 repairs the palm start state instead."
        })
        return
    raise AssertionError("v0.6 unexpectedly became green; inspect whether palm/contact semantics changed before updating this retained rejection proof")


if __name__ == "__main__":
    run()
