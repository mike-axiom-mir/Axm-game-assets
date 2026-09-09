#!/usr/bin/env python3
from native_hm08_rifle_grip_dqs import build_preferred_grip_dqs_pose


def run() -> None:
    mesh, evidence = build_preferred_grip_dqs_pose()
    assert evidence["schema"] == "axm.game-assets.hm08-rifle-grip-dqs.v0.8"
    assert len(mesh.vertices) == 13380 and len(mesh.faces) == 13378
    assert evidence["pose_reconstruction_max_error_m"] <= 1e-9, evidence
    assert evidence["finger_vertex_count"] > 2500, evidence
    assert evidence["nonfinger_max_delta_from_v0_7_lbs_m"] <= 1e-10, evidence
    radial = evidence["radial_preservation"]
    assert radial["samples"] > 500, radial
    assert radial["dqs_mean_abs_error_m"] < radial["lbs_mean_abs_error_m"], radial
    assert radial["relative_error"] < 1.0, radial
    penetration = evidence["grip_aabb_surface_penetration"]
    assert penetration["dqs_max_m"] <= penetration["lbs_max_m"] + 0.003, penetration
    assert evidence["truth"]["same_v0_7_skeleton_pose"] is True
    assert evidence["truth"]["same_v0_7_weights"] is True
    assert evidence["truth"]["dqs_applied_only_to_finger_influenced_vertices"] is True
    assert evidence["truth"]["production_deformation_claim"] is False
    print("HM08 GRIP DQS TEST PASS", {
        "reconstruction_error_m": evidence["pose_reconstruction_max_error_m"],
        "finger_vertices": evidence["finger_vertex_count"],
        "radial": radial,
        "penetration": penetration,
        "lbs_to_dqs_delta": evidence["finger_lbs_to_dqs_delta_m"],
    })


if __name__ == "__main__":
    run()
