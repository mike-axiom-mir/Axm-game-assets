#!/usr/bin/env python3

from native_hm08_full_rifle_pose import build_hm08_full_rifle_pose


def run() -> None:
    first_mesh, first = build_hm08_full_rifle_pose()
    second_mesh, second = build_hm08_full_rifle_pose()
    assert first == second
    assert first_mesh.vertices == second_mesh.vertices
    assert first_mesh.faces == second_mesh.faces

    assert first["schema"] == "axm.game-assets.hm08-full-rifle-pose.v0.1"
    assert first["pose_id"] == "full_rig_cross_chest_low_ready_v0.1"
    assert first["base_rig_schema"] == "axm.game-assets.hm08-humanoid-rig.v0.1"
    assert first["base_joint_count"] == 23
    assert first["augmented_joint_count"] == 25
    assert first["contact_markers"]["weight_influences"] == 0
    assert first["weapon"]["scale"] == [1.0, 1.0, 1.0]

    contact = first["contact"]
    assert contact["primary_position_error"] < 1e-6, contact
    assert contact["primary_orientation_error_deg"] < 1e-4, contact
    assert contact["support_position_error"] < 1e-6, contact
    assert contact["support_orientation_error_deg"] < 1e-4, contact

    for side in ("right", "left"):
        row = first["hand_geometry"][side]
        assert row["hand_vertices"] > 1000
        # This is deliberately looser than the exact marker gate: it measures
        # first-pass skin weights, not just solved skeleton math.
        assert row["centroid_to_marker_error_m"] < 0.080, row
        pose = first["pose"][side]
        assert 0.17 < pose["upper_bind_length_m"] < 0.25
        assert 0.22 < pose["forearm_bind_length_m"] < 0.32
        assert len(pose["palm_offset_from_wrist_m"]) == 3

    deformation = first["deformation"]
    assert deformation["finite"] is True
    assert deformation["bind_reconstruction_max_error_m"] <= 1e-9, deformation
    assert 0.05 < deformation["posed_max_displacement_m"] < 0.75, deformation
    edge = deformation["edge_ratio"]
    assert edge["p01"] > 0.55, edge
    assert edge["p99"] < 1.50, edge
    assert edge["max"] < 5.0, edge
    assert deformation["edges_over_2x"] < 120, deformation
    assert deformation["edges_under_half"] < 120, deformation

    truth = first["truth"]
    assert truth["single_full_body_motion_truth"] is True
    assert truth["arm_only_rig_required"] is False
    assert truth["canonical_body_mutated"] is False
    assert truth["rifle_scaled_to_fake_contact"] is False
    assert truth["production_rig_claim"] is False
    assert truth["production_skinning_claim"] is False
    assert truth["automatic_runtime_ik_claim"] is False

    print("HM08 FULL RIG RIFLE POSE TEST PASS", {
        "primary_error_mm": contact["primary_position_error"] * 1000.0,
        "support_error_mm": contact["support_position_error"] * 1000.0,
        "right_hand_mesh_error_mm": first["hand_geometry"]["right"]["centroid_to_marker_error_m"] * 1000.0,
        "left_hand_mesh_error_mm": first["hand_geometry"]["left"]["centroid_to_marker_error_m"] * 1000.0,
        "edge_ratio": edge,
        "max_displacement_m": deformation["posed_max_displacement_m"],
    })


if __name__ == "__main__":
    run()
