#!/usr/bin/env python3
from native_hm08_finger_pose_corrective import build_preferred_finger_pose_corrective


def run() -> None:
    mesh,evidence=build_preferred_finger_pose_corrective()
    assert evidence["schema"]=="axm.game-assets.hm08-finger-pose-corrective.v0.9"
    assert len(mesh.vertices)==13380 and len(mesh.faces)==13378
    assert evidence["finger_vertex_count"]>2500,evidence
    assert evidence["moved_finger_vertices"]>100,evidence
    assert evidence["max_vertex_correction_m"]<=evidence["correction_cap_m"]+1e-12,evidence
    assert evidence["nonfinger_max_delta_from_v0_7_lbs_m"]<=1e-10,evidence
    radial=evidence["radial_volume_error"]
    assert radial["joint_samples"]>=20,radial
    assert radial["eligible_deficit_joints"]>0,radial
    assert radial["improved_joints"]>0,radial
    assert radial["corrected_mean_abs_error_m"]<radial["lbs_mean_abs_error_m"],radial
    assert radial["relative_error"]<1.0,radial
    penetration=evidence["grip_aabb_surface_penetration"]
    assert penetration["corrected_max_m"]<=penetration["lbs_max_m"]+0.003,penetration
    assert evidence["truth"]["same_v0_7_contact_pose"] is True
    assert evidence["truth"]["same_v0_7_weights"] is True
    assert evidence["truth"]["corrective_driven_by_measured_bind_volume_deficit"] is True
    assert evidence["truth"]["production_corrective_claim"] is False
    print("HM08 FINGER POSE CORRECTIVE TEST PASS",{
        "moved_vertices":evidence["moved_finger_vertices"],
        "max_correction_m":evidence["max_vertex_correction_m"],
        "radial":radial,
        "penetration":penetration,
    })


if __name__=="__main__":
    run()
