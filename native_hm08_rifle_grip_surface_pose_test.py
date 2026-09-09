#!/usr/bin/env python3
from native_hm08_rifle_grip_surface_pose import build_preferred_grip_surface_finger_pose


def run() -> None:
    mesh, packet = build_preferred_grip_surface_finger_pose()
    summary = packet["contact_summary"]
    assert packet["schema"] == "axm.game-assets.hm08-rifle-grip-surface-pose.v0.7"
    assert len(mesh.vertices) == 13380 and len(mesh.faces) == 13378
    assert packet["finger_rig"]["total_joint_count"] == 53
    assert packet["finger_skin"]["max_influences"] <= 4
    assert packet["truth"]["weapon_transform_changed_from_v0_4"] is False
    assert packet["truth"]["internal_weapon_sockets_preserved"] is True
    assert packet["truth"]["palm_surface_derived_from_grip_geometry"] is True
    assert summary["surface_contact_open_finger_max_penetration_m"] < summary["original_internal_socket_open_finger_max_penetration_m"], summary
    assert summary["surface_contact_open_finger_max_penetration_m"] <= 0.006, summary
    assert summary["digits_within_penetration_budget"] == 10, summary
    assert summary["max_surface_penetration_m"] <= summary["penetration_budget_m"] + 1e-12, summary
    assert summary["final_mean_tip_surface_error_m"] < summary["baseline_mean_tip_surface_error_m"], summary
    assert summary["relative_tip_error"] < 0.85, summary
    assert summary["curled_digits"] >= 7, summary
    assert summary["finger_vertices_moved"] > 100
    assert summary["nonfinger_max_delta_from_surface_arm_pose_m"] <= 1e-10, summary
    assert packet["posed_skeleton_validation"]["status"] == "pass"
    assert packet["truth"]["production_grip_claim"] is False
    print("HM08 GRIP SURFACE POSE TEST PASS", summary)
    print("SELECTED PALM SURFACES", {side: packet["surface_contact_search"][side]["selected_face"] for side in ("right","left")})


if __name__ == "__main__":
    run()
