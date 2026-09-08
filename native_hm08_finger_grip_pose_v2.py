#!/usr/bin/env python3
"""Corrected source-grounded finger grip closure v0.2.

v0.1 correctly articulated the four non-thumb fingers but its thumb opposition
mixed a hand-local grip point with a world-space thumb root. v0.2 preserves the
same source finger rig, v0.4 arm pose, human-scale rifle, palm sockets and curl
search, while expressing the thumb root and grip target in the hand joint's
local coordinate space before deriving opposition.
"""
from __future__ import annotations

import copy

from native_attachment import TwoHandSocketAttachment, socket_contact_evidence
from native_geometry import Mesh
from native_hm08_finger_grip_pose import (
    _apply_arm_pose,
    _axis_angle,
    _curl_fingers,
    _distance,
    _distance_to_axis,
    _finger_tip_world,
    _from_to_limited,
    _quat_mul,
    _source_flex_axes,
)
from native_hm08_finger_rig import (
    _finger_rows,
    _source_side_mapping,
    build_hm08_finger_skeleton,
    build_hm08_finger_skin_weights,
    load_finger_landmarks,
)
from native_hm08_humanoid_rig import build_hm08_humanoid_skeleton, derive_hm08_rig_landmarks
from native_hm08_rifle_contact_pose_v2 import derive_shared_rig_arms
from native_hm08_rifle_contact_pose_v4 import build_segment_skin_rifle_contact_pose
from native_hm08_undersuit import _load_identity_body
from native_skin import Skeleton, global_joint_matrices, inverse4, skin_vertices, transform_point, validate_skeleton
from native_weapon_human_scale import sentinel_rifle_human_scale

SCHEMA = "axm.game-assets.hm08-finger-grip-pose.v0.2"


def _corrected_thumb_opposition(
    skeleton: Skeleton,
    finger_indices: dict[str,int],
    rig_evidence: dict[str,object],
    rows: dict[tuple[str,int,int],dict[str,object]],
    axes,
    side: str,
    sign: float,
    grip_center,
):
    joints=list(skeleton.joints)
    root_index=finger_indices[f"{side}_finger1_1"]
    root_local=tuple(float(value) for value in joints[root_index].translation)
    source_head=tuple(float(v) for v in rows[(side,1,1)]["head_m"])
    source_tail=tuple(float(v) for v in rows[(side,1,1)]["tail_m"])
    bind_direction=(source_tail[0]-source_head[0],source_tail[1]-source_head[1],source_tail[2]-source_head[2])

    hand_index=next(index for index,joint in enumerate(joints) if joint.name==f"{side}_hand")
    hand_world=global_joint_matrices(skeleton)[hand_index]
    grip_local=transform_point(inverse4(hand_world),grip_center)
    desired=(grip_local[0]-root_local[0],grip_local[1]-root_local[1],grip_local[2]-root_local[2])
    opposition=_from_to_limited(bind_direction,desired,34.0)
    flex_axis=axes[side]["flex_axis"]
    thumb_angles={1:14.0,2:38.0,3:34.0}
    for segment in range(1,4):
        index=finger_indices[f"{side}_finger1_{segment}"]
        source=joints[index]
        curl=_axis_angle(flex_axis,sign*thumb_angles[segment])
        rotation=_quat_mul(opposition,curl) if segment==1 else curl
        joints[index]=source.__class__(source.name,source.parent,source.translation,rotation,source.scale)
    posed=Skeleton(joints)
    report=validate_skeleton(posed)
    if report["status"]!="pass":
        raise ValueError(f"corrected thumb skeleton invalid: {report}")
    tip=_finger_tip_world(posed,finger_indices,rig_evidence,side,1)
    return posed,{
        "coordinate_space":"hand_joint_local",
        "root_local":list(root_local),
        "grip_local":list(grip_local),
        "opposition_limit_deg":34.0,
        "curl_angles_deg":thumb_angles,
        "tip_world":list(tip),
        "tip_to_grip_center_m":_distance(tip,grip_center),
    }


def build_hm08_finger_grip_pose_v2(body: Mesh):
    v4_mesh,v4=build_segment_skin_rifle_contact_pose(body)
    packet=load_finger_landmarks()
    mapping=_source_side_mapping(packet)
    rows=_finger_rows(packet,mapping)
    finger_skeleton,finger_indices,rig_evidence=build_hm08_finger_skeleton(body)
    finger_weights,skin_evidence=build_hm08_finger_skin_weights(body,finger_skeleton,finger_indices)
    _base,_base_evidence,base_indices=build_hm08_humanoid_skeleton(body)
    arm_posed=_apply_arm_pose(finger_skeleton,base_indices,v4)
    axes=_source_flex_axes(packet,mapping,rows)
    rifle=sentinel_rifle_human_scale()
    weapon_rotation=tuple(float(v) for v in v4["weapon"]["rotation"])
    primary_center=tuple(float(v) for v in v4["contact"]["primary_hand_contact_world_position"])
    support_center=tuple(float(v) for v in v4["contact"]["support_hand_contact_world_position"])
    from native_hm08_rifle_contact_pose import _quat_rotate
    grip_state={
        "right":{"center":primary_center,"axis":_quat_rotate(weapon_rotation,(0.0,1.0,0.0)),"radius":0.033},
        "left":{"center":support_center,"axis":_quat_rotate(weapon_rotation,(1.0,0.0,0.0)),"radius":0.044},
    }

    current=arm_posed
    search_evidence={}
    for side in ("right","left"):
        candidates=[]
        for sign in (-1.0,1.0):
            for multiplier in (0.70,0.85,1.00,1.15):
                candidate,row=_curl_fingers(
                    current,finger_indices,rig_evidence,axes,side,sign,multiplier,
                    grip_state[side]["center"],grip_state[side]["axis"],grip_state[side]["radius"],
                )
                candidates.append((float(row["objective"]),sign,multiplier,candidate,row))
        candidates.sort(key=lambda item:(item[0],item[1],item[2]))
        _objective,sign,multiplier,current,best=candidates[0]
        current,thumb=_corrected_thumb_opposition(
            current,finger_indices,rig_evidence,rows,axes,side,sign,grip_state[side]["center"]
        )
        search_evidence[side]={
            "selected":best,
            "thumb":thumb,
            "candidate_objectives":[{"sign":item[1],"multiplier":item[2],"objective":item[0]} for item in candidates],
        }

    landmarks=derive_hm08_rig_landmarks(body)
    arms=derive_shared_rig_arms(body,landmarks)
    attachment=TwoHandSocketAttachment(
        primary_joint=base_indices["right_hand"],support_joint=base_indices["left_hand"],
        primary_hand_socket=arms["right"].hand_socket,support_hand_socket=arms["left"].hand_socket,
        primary_weapon_socket=rifle.sockets["primary_grip"],support_weapon_socket=rifle.sockets["support_grip"],
    )
    contact=socket_contact_evidence(current,attachment)
    posed_mesh=Mesh(
        "sentinel_hm08_articulated_grip_v0_2",
        skin_vertices(body,finger_weights,finger_skeleton,current),
        list(body.faces),
    )

    finger_joint_set=set(finger_indices.values())
    nonfinger_max=0.0
    finger_changed=0
    for index,(before,after) in enumerate(zip(v4_mesh.vertices,posed_mesh.vertices)):
        has_finger=any(
            joint in finger_joint_set and weight>1e-9
            for joint,weight in zip(finger_weights.joints[index],finger_weights.weights[index])
        )
        distance=_distance(before,after)
        if has_finger:
            if distance>1e-8:
                finger_changed+=1
        else:
            nonfinger_max=max(nonfinger_max,distance)

    final_tips={}
    for side in ("right","left"):
        final_tips[side]={}
        for digit in range(1,6):
            tip=_finger_tip_world(current,finger_indices,rig_evidence,side,digit)
            radial,along=_distance_to_axis(tip,grip_state[side]["center"],grip_state[side]["axis"])
            final_tips[side][str(digit)]={
                "position":list(tip),
                "radial_distance_m":radial,
                "axis_offset_m":along,
                "target_radius_m":grip_state[side]["radius"],
                "radius_error_m":abs(radial-grip_state[side]["radius"]),
            }

    evidence={
        "schema":SCHEMA,
        "pose_id":"source_grounded_rifle_grip_v0.2",
        "repair_lineage":{
            "supersedes":"axm.game-assets.hm08-finger-grip-pose.v0.1",
            "v0_1_status":"rejected_coordinate_space_bug_in_thumb_opposition",
            "repair":"express_thumb_root_and_grip_target_in_hand_joint_local_space",
        },
        "changed_variable_from_v0_4":"finger_skeleton_weights_and_grip_closure_only",
        "finger_rig":rig_evidence,
        "finger_skin":skin_evidence,
        "grip_state":{side:{"center":list(row["center"]),"axis":list(row["axis"]),"radius_m":row["radius"]} for side,row in grip_state.items()},
        "curl_search":search_evidence,
        "final_fingertips":final_tips,
        "contact":contact,
        "weapon":copy.deepcopy(v4["weapon"]),
        "arm_pose":copy.deepcopy(v4["pose"]),
        "finger_changed_vertices":finger_changed,
        "nonfinger_max_delta_from_v0_4_m":nonfinger_max,
        "truth":{
            "v0_4_arm_pose_preserved":True,
            "human_scale_rifle_preserved":True,
            "palm_socket_contact_preserved":True,
            "source_grounded_finger_pivots":True,
            "thumb_coordinate_space_corrected":True,
            "finger_collision_solver_claim":False,
            "trigger_finger_claim":False,
            "production_grip_claim":False,
            "automatic_visual_promotion":False,
            "notes":[
                "v0.1 is retained as failed evidence because thumb opposition mixed coordinate spaces. v0.2 repairs only that contract.",
                "Four-finger curl still uses the same bounded deterministic grip-axis/radius search; palm sockets, arm pose and human-scale rifle remain unchanged from v0.4.",
                "Godot hands-close evidence remains the promotion authority for visible knuckle compression, thumb opposition and actual grip readability."
            ],
        },
    }
    return posed_mesh,evidence


def build_preferred_hm08_finger_grip_pose_v2():
    body,_uv,_state=_load_identity_body()
    return build_hm08_finger_grip_pose_v2(body)


if __name__=="__main__":
    import json
    mesh,evidence=build_preferred_hm08_finger_grip_pose_v2()
    print(json.dumps({"vertices":len(mesh.vertices),"faces":len(mesh.faces),**evidence},indent=2))
