#!/usr/bin/env python3
"""Rifle contact v0.4: same v0.3 pose, bone-segment arm skin only.

This is a strict deformation A/B. The human-scale rifle, shared 23-joint rig,
palm sockets, joint rotations and contact targets come directly from v0.3.
Only the shared rig's arm weights change from point-distance v0.1 to segment
weights v0.2. No contact or weapon transform is repaired in this layer.
"""
from __future__ import annotations

import copy

from native_geometry import Mesh, bounds
from native_hm08_humanoid_rig import build_hm08_humanoid_skeleton, derive_hm08_rig_landmarks
from native_hm08_humanoid_skin_v2 import build_hm08_skin_weights_v2
from native_hm08_rifle_contact_pose import _centroid, _distance
from native_hm08_rifle_contact_pose_v2 import derive_shared_rig_arms
from native_hm08_rifle_contact_pose_v3 import build_human_scale_rifle_contact_pose
from native_hm08_undersuit import _load_identity_body
from native_skin import Joint, Skeleton, skin_vertices, validate_skeleton

SCHEMA = "axm.game-assets.hm08-rifle-contact-pose.v0.4"


def _quat(row) -> tuple[float,float,float,float]:
    return tuple(float(value) for value in row)  # type: ignore[return-value]


def build_segment_skin_rifle_contact_pose(body_m: Mesh) -> tuple[Mesh,dict[str,object]]:
    _v3_mesh,v3=build_human_scale_rifle_contact_pose(body_m)
    landmarks=derive_hm08_rig_landmarks(body_m)
    bind,rig_evidence,indices=build_hm08_humanoid_skeleton(body_m)
    weights,skin_evidence=build_hm08_skin_weights_v2(body_m,bind,landmarks,indices)
    arms=derive_shared_rig_arms(body_m,landmarks)

    joints=list(bind.joints)
    for side in ("right","left"):
        row=v3["pose"][side]
        upper=indices[f"{side}_upper_arm"]
        fore=indices[f"{side}_forearm"]
        hand=indices[f"{side}_hand"]
        source=joints[upper]
        joints[upper]=Joint(source.name,source.parent,source.translation,_quat(row["shoulder_rotation"]),source.scale)
        source=joints[fore]
        joints[fore]=Joint(source.name,source.parent,source.translation,_quat(row["elbow_rotation"]),source.scale)
        source=joints[hand]
        joints[hand]=Joint(source.name,source.parent,source.translation,_quat(row["hand_rotation"]),source.scale)
    posed=Skeleton(joints)
    report=validate_skeleton(posed)
    if report["status"]!="pass":
        raise ValueError(f"v0.4 reconstructed pose skeleton invalid: {report}")

    posed_mesh=Mesh(
        "sentinel_hm08_segment_skin_rifle_contact_v0_4",
        skin_vertices(body_m,weights,bind,posed),
        list(body_m.faces),
    )
    contact=v3["contact"]
    hand_visual={}
    for side in ("right","left"):
        centroid=_centroid(posed_mesh,arms[side].hand_vertex_indices)
        key="primary_hand_contact_world_position" if side=="right" else "support_hand_contact_world_position"
        socket=tuple(float(value) for value in contact[key])
        hand_visual[side]={
            "posed_hand_region_centroid":list(centroid),
            "hand_socket_world":list(socket),
            "centroid_to_socket_error_m":_distance(centroid,socket),
        }

    rotated={
        indices["right_upper_arm"],indices["right_forearm"],indices["right_hand"],
        indices["left_upper_arm"],indices["left_forearm"],indices["left_hand"],
    }
    stationary_max=0.0
    moved=0
    for i,(before,after) in enumerate(zip(body_m.vertices,posed_mesh.vertices)):
        distance=_distance(before,after)
        if distance>1e-12:
            moved+=1
        active=any(joint in rotated and weight>1e-9 for joint,weight in zip(weights.joints[i],weights.weights[i]))
        if not active:
            stationary_max=max(stationary_max,distance)

    lo,hi=bounds(body_m)
    height=hi[1]-lo[1]
    head_indices=[i for i,p in enumerate(body_m.vertices) if p[1]>=lo[1]+height*0.84]
    lower_indices=[i for i,p in enumerate(body_m.vertices) if p[1]<=lo[1]+height*0.50]
    head_max=max(_distance(body_m.vertices[i],posed_mesh.vertices[i]) for i in head_indices)
    lower_max=max(_distance(body_m.vertices[i],posed_mesh.vertices[i]) for i in lower_indices)

    packet=copy.deepcopy(v3)
    packet["schema"]=SCHEMA
    packet["pose_id"]="cross_chest_low_ready_segment_skin_v0.4"
    packet["shared_rig"]["skeleton_evidence"]=rig_evidence
    packet["shared_rig"]["skin_evidence"]=skin_evidence
    packet["hand_visual_contact"]=hand_visual
    packet["moved_vertices"]=moved
    packet["stationary_weight_region_max_displacement_m"]=stationary_max
    packet["head_max_displacement_m"]=head_max
    packet["lower_body_max_displacement_m"]=lower_max
    packet["changed_variable_from_v0_3"]="arm_skin_weights_only"
    packet["v0_3_hand_visual_contact"]=v3["hand_visual_contact"]
    packet["truth"]={
        "uses_shared_full_body_rig":True,
        "character_hand_sockets_explicit":True,
        "human_scale_rifle_preserved":True,
        "joint_pose_preserved_from_v0_3":True,
        "segment_skin_v0_2_used":True,
        "finger_chain_claim":False,
        "production_skinning_claim":False,
        "automatic_visual_promotion":False,
        "notes":[
            "v0.4 reconstructs the exact v0.3 shared-rig joint rotations and contact target state, then reskins the same canonical body with bone-segment arm weights v0.2.",
            "Any Godot visual difference from v0.3 is therefore attributable to arm skinning, not weapon dimensions, contact sockets or pose target changes.",
            "Hands remain rigid open/relaxed geometry because explicit finger chains and grip closure are intentionally not claimed yet."
        ],
    }
    return posed_mesh,packet


def build_preferred_segment_skin_rifle_contact_pose():
    body,_uv,_state=_load_identity_body()
    return build_segment_skin_rifle_contact_pose(body)


if __name__=="__main__":
    import json
    mesh,packet=build_preferred_segment_skin_rifle_contact_pose()
    print(json.dumps({"vertices":len(mesh.vertices),"faces":len(mesh.faces),**packet},indent=2))
