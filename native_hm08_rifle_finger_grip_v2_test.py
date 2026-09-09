#!/usr/bin/env python3
from native_hm08_rifle_finger_grip_v2 import build_preferred_penetration_bounded_finger_grip


def run() -> None:
    mesh, packet = build_preferred_penetration_bounded_finger_grip()
    summary = packet["contact_summary"]
    assert packet["schema"] == "axm.game-assets.hm08-rifle-finger-grip.v0.6"
    assert len(mesh.vertices) == 13380 and len(mesh.faces) == 13378
    assert packet["finger_rig"]["total_joint_count"] == 53
    assert packet["finger_skin"]["max_influences"] <= 4
    assert len(packet["digit_contact"]) == 10
    assert summary["digits_within_penetration_budget"] == 10, summary
    assert summary["max_surface_penetration_m"] <= summary["penetration_budget_m"] + 1e-12, summary
    assert summary["final_mean_tip_surface_error_m"] < summary["baseline_mean_tip_surface_error_m"], summary
    assert summary["relative_tip_error"] < 0.70, summary
    assert summary["digits_not_worse"] >= 8, summary
    assert summary["curled_digits"] >= 8, summary
    assert summary["finger_vertices_moved"] > 100
    assert summary["nonfinger_max_delta_from_arm_only_m"] <= 1e-10, summary
    assert packet["truth"]["arm_pose_changed_from_v0_4"] is False
    assert packet["truth"]["weapon_transform_changed_from_v0_4"] is False
    assert packet["truth"]["v0_5_preserved_as_evidence"] is True
    assert packet["truth"]["production_grip_claim"] is False
    print("HM08 FINGER GRIP V0.6 TEST PASS", summary)
    print("WORST DIGITS", summary["worst_digits"])


if __name__ == "__main__":
    run()
