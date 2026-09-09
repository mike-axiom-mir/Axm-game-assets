#!/usr/bin/env python3
from dataclasses import replace

from native_hm08_humanoid_rig import build_hm08_humanoid_skeleton, derive_hm08_rig_landmarks
from native_hm08_humanoid_skin_v2 import build_hm08_skin_weights_v2
from native_hm08_rifle_contact_pose import _distance
from native_hm08_rifle_contact_pose_v5 import (
    SCALE_CANDIDATES,
    _reconstruct_v4_on_finger_rig,
    build_preferred_finger_grip_rifle_contact_pose,
)
from native_hm08_undersuit import _load_identity_body
from native_skin import Skeleton, global_joint_matrices, skin_vertices
from native_geometry import Mesh


def _max_error(a: Mesh,b: Mesh):
    rows=[(_distance(x,y),index) for index,(x,y) in enumerate(zip(a.vertices,b.vertices))]
    return max(rows)


def _debug_v4_reconstruction() -> None:
    body,_uv,_state=_load_identity_body()
    v4_mesh,v4,extended_bind,extended_weights,_indices,rig_evidence,_skin_evidence,open_skeleton,open_mesh=_reconstruct_v4_on_finger_rig(body)

    landmarks=derive_hm08_rig_landmarks(body)
    base_bind,_rig,base_indices=build_hm08_humanoid_skeleton(body)
    base_weights,_skin=build_hm08_skin_weights_v2(body,base_bind,landmarks,base_indices)
    joints=list(base_bind.joints)
    for side in ("right","left"):
        row=v4["pose"][side]
        for suffix,key in (("upper_arm","shoulder_rotation"),("forearm","elbow_rotation"),("hand","hand_rotation")):
            index=base_indices[f"{side}_{suffix}"]
            joints[index]=replace(joints[index],rotation=tuple(float(v) for v in row[key]))
    base_pose=Skeleton(joints)
    base_mesh=Mesh("debug_base_v4",skin_vertices(body,base_weights,base_bind,base_pose),list(body.faces))

    base_vs_v4=_max_error(base_mesh,v4_mesh)
    extended_vs_base=_max_error(open_mesh,base_mesh)
    extended_vs_v4=_max_error(open_mesh,v4_mesh)
    max_index=extended_vs_base[1]
    finger_joint_set=set(rig_evidence["finger_indices"].values())
    finger_active=any(joint in finger_joint_set and weight>1e-9 for joint,weight in zip(extended_weights.joints[max_index],extended_weights.weights[max_index]))

    base_globals=global_joint_matrices(base_pose)
    extended_globals=global_joint_matrices(open_skeleton)
    base_joint_matrix_error=0.0
    for index in range(23):
        for row in range(4):
            for col in range(4):
                base_joint_matrix_error=max(base_joint_matrix_error,abs(base_globals[index][row][col]-extended_globals[index][row][col]))

    print("V5 V4 REPRO DEBUG",{
        "base_vs_v4_max_m":base_vs_v4,
        "extended_vs_base_max_m":extended_vs_base,
        "extended_vs_v4_max_m":extended_vs_v4,
        "first_23_bind_equal":extended_bind.joints[:23]==base_bind.joints,
        "first_23_pose_equal":open_skeleton.joints[:23]==base_pose.joints,
        "first_23_global_matrix_max_error":base_joint_matrix_error,
        "max_vertex_index":max_index,
        "max_vertex":body.vertices[max_index],
        "finger_active_at_max":finger_active,
        "base_weight_row":(base_weights.joints[max_index],base_weights.weights[max_index]),
        "extended_weight_row":(extended_weights.joints[max_index],extended_weights.weights[max_index]),
    })


def run() -> None:
    _debug_v4_reconstruction()
    first_mesh, first = build_preferred_finger_grip_rifle_contact_pose()
    second_mesh, second = build_preferred_finger_grip_rifle_contact_pose()
    assert first == second
    assert first_mesh.vertices == second_mesh.vertices
    assert first_mesh.faces == second_mesh.faces
    assert all(first["acceptance"].values()), first["acceptance"]

    assert first["schema"] == "axm.game-assets.hm08-rifle-contact-pose.v0.5"
    assert first["pose_id"] == "cross_chest_low_ready_finger_grip_v0.5"
    assert first["shared_rig"]["joint_count"] == 53
    assert first["shared_rig"]["finger_joint_count"] == 30
    assert first["shared_rig"]["finger_rig_evidence"]["base_joint_count"] == 23
    assert first["shared_rig"]["finger_skin_evidence"]["base_skin_schema"] == "axm.game-assets.hm08-humanoid-skin.v0.2"

    grip = first["finger_grip"]
    assert grip["open_pose_vs_v0_4_nonfinger_max_error_m"] < 1e-9
    assert grip["open_pose_vs_v0_4_max_error_m"] < 1e-6
    assert first["weapon"]["scale"] == [1.0,1.0,1.0]
    assert float(first["contact"]["primary_position_error"]) < 1e-8
    assert float(first["contact"]["support_position_error"]) < 1e-6

    assert grip["curl_moved_finger_vertices"] > 200
    assert 0.003 < grip["finger_curl_max_displacement_m"] < 0.12
    assert grip["nonfinger_curl_max_displacement_m"] < 1e-8
    assert grip["head_curl_max_displacement_m"] < 1e-9
    assert grip["lower_body_curl_max_displacement_m"] < 1e-9
    assert grip["minimum_fingertip_improvement_m"] > 1e-6
    assert grip["mean_fingertip_improvement_m"] > 1e-4

    for side in ("right","left"):
        choice = grip["choices"][side]
        assert choice["curled_tip_mean_m"] < choice["open_tip_mean_m"], choice
        assert choice["mean_improvement_m"] > 0.0
        assert set(choice["digits"]) == {"1","2","3","4","5"}
        for digit, row in choice["digits"].items():
            assert row["scale"] in SCALE_CANDIDATES, row
            assert row["curled_tip_to_socket_m"] < row["open_tip_to_socket_m"], (side,digit,row)
            assert row["improvement_m"] > 1e-6
            assert len(row["segments"]) == 3
            assert all(0.0 <= segment["applied_angle_deg"] <= segment["cap_deg"] + 1e-9 for segment in row["segments"])
        assert grip["finger_surface"][side]["vertex_count"] > 150
        assert grip["finger_surface"][side]["centroid_to_socket_m"] < 0.09

    assert first["truth"]["v0_4_arm_pose_preserved"] is True
    assert first["truth"]["human_scale_rifle_preserved"] is True
    assert first["truth"]["source_grounded_finger_chains"] is True
    assert first["truth"]["production_grip_claim"] is False
    assert first["truth"]["automatic_visual_promotion"] is False

    print("HM08 FINGER GRIP V0.5 TEST PASS", {
        "joints": first["shared_rig"]["joint_count"],
        "open_vs_v4_um": grip["open_pose_vs_v0_4_max_error_m"] * 1e6,
        "moved_finger_vertices": grip["curl_moved_finger_vertices"],
        "max_curl_mm": grip["finger_curl_max_displacement_m"] * 1000.0,
        "minimum_tip_improvement_mm": grip["minimum_fingertip_improvement_m"] * 1000.0,
        "right_tip_mean_mm": [grip["choices"]["right"]["open_tip_mean_m"]*1000.0, grip["choices"]["right"]["curled_tip_mean_m"]*1000.0],
        "left_tip_mean_mm": [grip["choices"]["left"]["open_tip_mean_m"]*1000.0, grip["choices"]["left"]["curled_tip_mean_m"]*1000.0],
    })


if __name__ == "__main__":
    run()
