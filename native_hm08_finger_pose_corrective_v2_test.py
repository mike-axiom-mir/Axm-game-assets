#!/usr/bin/env python3
from native_hm08_finger_pose_corrective_v2 import build_preferred_pointwise_finger_pose_corrective


def run() -> None:
    mesh,evidence=build_preferred_pointwise_finger_pose_corrective()
    assert evidence["schema"]=="axm.game-assets.hm08-finger-pose-corrective.v0.10"
    assert len(mesh.vertices)==13380 and len(mesh.faces)==13378
    assert evidence["finger_vertex_count"]>2500,evidence
    assert evidence["moved_finger_vertices"]>300,evidence
    assert evidence["active_bulge_joints"]>0,evidence
    assert evidence["max_vertex_correction_m"]<=evidence["correction_cap_m"]+1e-12,evidence
    assert evidence["nonfinger_max_delta_from_v0_7_lbs_m"]<=1e-10,evidence
    radial=evidence["pointwise_radial_error"]
    assert radial["samples"]>500,radial
    assert radial["improved_pairs"]>0,radial
    assert radial["corrected_mean_abs_error_m"]<radial["lbs_mean_abs_error_m"],radial
    assert radial["relative_error"]<1.0,radial
    penetration=evidence["grip_aabb_surface_penetration"]
    assert penetration["corrected_max_m"]<=penetration["lbs_max_m"]+0.003,penetration
    assert evidence["truth"]["same_v0_7_contact_pose"] is True
    assert evidence["truth"]["same_v0_7_weights"] is True
    assert evidence["truth"]["flexion_outer_knuckle_bulge_used"] is True
    assert evidence["truth"]["v0_9_conservative_attempt_preserved"] is True
    assert evidence["truth"]["production_corrective_claim"] is False
    print("HM08 FINGER CORRECTIVE V0.10 TEST PASS",{
        "moved_vertices":evidence["moved_finger_vertices"],
        "max_correction_m":evidence["max_vertex_correction_m"],
        "active_bulge_joints":evidence["active_bulge_joints"],
        "radial":radial,
        "penetration":penetration,
        "top_joints":evidence["top_corrective_joints"],
    })


if __name__=="__main__":
    run()
