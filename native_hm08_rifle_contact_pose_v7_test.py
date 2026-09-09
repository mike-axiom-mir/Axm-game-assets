#!/usr/bin/env python3

from native_hm08_grip_palm_diagnostic import build_grip_palm_diagnostic
from native_hm08_rifle_contact_pose_v7 import PALM_SURFACE_CLEARANCE_M, build_preferred_physical_grip_rifle_contact_pose


def run() -> None:
    diagnostic = build_grip_palm_diagnostic()
    assert diagnostic["schema"] == "axm.game-assets.hm08-grip-palm-diagnostic.v0.1"
    assert diagnostic["truth"]["diagnostic_only"] is True
    for side in ("right", "left"):
        row = diagnostic["rows"][side]
        assert abs(row["palm_socket_surface_gap"]["surface_gap_m"] - PALM_SURFACE_CLEARANCE_M) < 1e-12, row
        assert row["root_surface_gap_m_range"][0] > 0.010, row
        assert row["palm_normal_to_grip_inward_angle_deg"] > 65.0, row
    assert diagnostic["rows"]["right"]["palm_normal_to_grip_inward_angle_deg"] > 70.0
    assert diagnostic["rows"]["left"]["palm_normal_to_grip_inward_angle_deg"] > 70.0

    try:
        build_preferred_physical_grip_rifle_contact_pose()
    except ValueError as exc:
        message = str(exc)
        assert "no collision-safe v0.7 finger candidate for right digit 3" in message, message
        assert "0.009947" in message, message
        print("HM08 PHYSICAL GRIP V0.7 EXPECTED REJECTION PASS", {
            "reason": "palm socket reaches the near surface but the palm plane remains roughly seventy degrees edge-on to the grip",
            "right_palm_angle_deg": diagnostic["rows"]["right"]["palm_normal_to_grip_inward_angle_deg"],
            "left_palm_angle_deg": diagnostic["rows"]["left"]["palm_normal_to_grip_inward_angle_deg"],
            "minimum_root_surface_gap_mm": min(
                diagnostic["rows"]["right"]["root_surface_gap_m_range"][0],
                diagnostic["rows"]["left"]["root_surface_gap_m_range"][0],
            ) * 1000.0,
            "minimum_observed_right_middle_penetration_mm_approx": 9.947,
            "truth": "v0.7 is retained as negative evidence. The next repair must correct wrist/palm-plane orientation before finger curl, not weaken penetration or move the rifle."
        })
        return
    raise AssertionError("v0.7 unexpectedly became green; inspect whether palm orientation/contact semantics changed before updating this rejection proof")


if __name__ == "__main__":
    run()
