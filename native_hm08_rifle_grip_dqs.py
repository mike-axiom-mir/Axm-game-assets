#!/usr/bin/env python3
"""Finger-local DQS deformation for the proven v0.7 Sentinel grip pose v0.8.

The v0.7 surface-contact/finger-wrap skeleton is reconstructed from its receipts
and verified against the v0.7 LBS mesh. DQS is then evaluated with the exact
same 53-joint skeleton and four-weight rows, but only vertices influenced by the
30 appended finger joints are taken from the DQS result. Every non-finger vertex
remains byte-for-position the v0.7 LBS output.
"""
from __future__ import annotations

from dataclasses import replace

from native_dual_quaternion_skin import dual_quaternion_skin_vertices
from native_geometry import Mesh, bounds
from native_hm08_finger_rig import _segment_distance, build_hm08_finger_skeleton, build_hm08_finger_skin_weights
from native_hm08_rifle_contact_pose import _cross, _distance, _dot, _length, _mul, _normalize, _quat_conjugate, _quat_rotate, _sub
from native_hm08_rifle_finger_grip import _axis_angle, _curl_profiles, _global_rotations, _local_to_weapon_world, _quat, _world_to_weapon_local, _aabb_sdf
from native_hm08_rifle_grip_surface_pose import _apply_arm_rows, build_grip_surface_finger_pose
from native_hm08_undersuit import _load_identity_body
from native_skin import Skeleton, global_joint_matrices, skin_vertices, transform_point, validate_skeleton
from native_weapon_human_scale import sentinel_rifle_human_scale

SCHEMA="axm.game-assets.hm08-rifle-grip-dqs.v0.8"


def _reconstruct_v07_skeleton(body:Mesh,packet:dict[str,object]):
    bind,finger_indices,rig_evidence=build_hm08_finger_skeleton(body)
    weights,skin_evidence=build_hm08_finger_skin_weights(body,bind,finger_indices)
    indices={joint.name:index for index,joint in enumerate(bind.joints)}
    arm_pose=_apply_arm_rows(bind,indices,packet["selected_arm_pose"])
    joints=list(arm_pose.joints)
    arm_rotations=_global_rotations(arm_pose)
    weapon=packet["weapon"]
    weapon_rotation=_quat(weapon["rotation"])
    rifle=sentinel_rifle_human_scale()
    component_for_side={"right":"primary_grip","left":"foregrip"}
    profiles=_curl_profiles()

    for side in ("right","left"):
        box_lo,box_hi=bounds(rifle.components[component_for_side[side]])
        center_local=tuple((box_lo[i]+box_hi[i])*0.5 for i in range(3))
        center_world=_local_to_weapon_world(center_local,tuple(float(v) for v in weapon["translation"]),weapon_rotation)
        for digit in range(1,6):
            current=Skeleton(list(joints))
            matrices=global_joint_matrices(current)
            first=finger_indices[f"{side}_finger{digit}_1"]
            second=finger_indices[f"{side}_finger{digit}_2"]
            first_world=transform_point(matrices[first],(0.0,0.0,0.0))
            second_world=transform_point(matrices[second],(0.0,0.0,0.0))
            segment=_sub(second_world,first_world)
            grip_axis_world=_quat_rotate(weapon_rotation,(0.0,1.0,0.0))
            toward=_sub(center_world,first_world)
            radial=_sub(toward,_mul(grip_axis_world,_dot(toward,grip_axis_world)))
            if _length(radial)<=1e-8:radial=toward
            bend_axis=_cross(segment,radial)
            if _length(bend_axis)<=1e-8:bend_axis=_cross(segment,grip_axis_world)
            bend_axis=_normalize(bend_axis)
            local_axes={}
            for segment_index in range(1,4):
                joint_index=finger_indices[f"{side}_finger{digit}_{segment_index}"]
                parent=current.joints[joint_index].parent
                parent_rotation=(0.0,0.0,0.0,1.0) if parent is None else arm_rotations[parent]
                local_axes[segment_index]=_quat_rotate(_quat_conjugate(parent_rotation),bend_axis)
            receipt=packet["digit_contact"][f"{side}:{digit}"]
            strength=float(receipt["curl_strength"]);direction=int(receipt["curl_direction"])
            for segment_index,base_angle in enumerate(profiles[digit],start=1):
                joint_index=finger_indices[f"{side}_finger{digit}_{segment_index}"]
                joints[joint_index]=replace(joints[joint_index],rotation=_axis_angle(local_axes[segment_index],direction*base_angle*strength))
    posed=Skeleton(joints)
    report=validate_skeleton(posed)
    if report["status"]!="pass":raise ValueError(f"reconstructed v0.7 skeleton invalid: {report}")
    return bind,posed,weights,finger_indices,rig_evidence,skin_evidence


def _segment_endpoints(skeleton:Skeleton,finger_indices:dict[str,int],tip_offsets:dict[str,object],side:str,digit:int,segment:int):
    matrices=global_joint_matrices(skeleton)
    index=finger_indices[f"{side}_finger{digit}_{segment}"]
    start=transform_point(matrices[index],(0.0,0.0,0.0))
    if segment<3:
        child=finger_indices[f"{side}_finger{digit}_{segment+1}"]
        end=transform_point(matrices[child],(0.0,0.0,0.0))
    else:
        local=tuple(float(v) for v in tip_offsets[f"{side}_finger{digit}_tip"])
        end=transform_point(matrices[index],local)
    return start,end


def build_grip_dqs_pose(body:Mesh)->tuple[Mesh,dict[str,object]]:
    lbs_mesh,v07=build_grip_surface_finger_pose(body)
    bind,posed,weights,finger_indices,rig_evidence,skin_evidence=_reconstruct_v07_skeleton(body,v07)
    reconstructed_lbs=skin_vertices(body,weights,bind,posed)
    reconstruction_error=max(_distance(a,b) for a,b in zip(reconstructed_lbs,lbs_mesh.vertices))
    if reconstruction_error>1e-9:raise ValueError(f"v0.7 pose reconstruction drift: {reconstruction_error}")
    dqs_all=dual_quaternion_skin_vertices(body,weights,bind,posed)
    base_joint_count=int(rig_evidence["base_joint_count"])
    finger_vertices={
        index for index,(joint_row,weight_row) in enumerate(zip(weights.joints,weights.weights))
        if any(joint>=base_joint_count and weight>1e-9 for joint,weight in zip(joint_row,weight_row))
    }
    hybrid=list(lbs_mesh.vertices)
    for index in finger_vertices:hybrid[index]=dqs_all[index]
    dqs_mesh=Mesh("sentinel_hm08_rifle_grip_dqs_v0_8",hybrid,list(body.faces))

    nonfinger_max=max((_distance(a,b) for i,(a,b) in enumerate(zip(lbs_mesh.vertices,dqs_mesh.vertices)) if i not in finger_vertices),default=0.0)
    finger_delta=[_distance(lbs_mesh.vertices[i],dqs_mesh.vertices[i]) for i in finger_vertices]

    # Compare radial thickness preservation against the source-grounded segment
    # associated with the strongest appended-finger influence at each vertex.
    bind_segments={};posed_segments={}
    for side in ("left","right"):
        for digit in range(1,6):
            for segment in range(1,4):
                key=(side,digit,segment)
                bind_segments[key]=_segment_endpoints(bind,finger_indices,rig_evidence["tip_local_offsets"],side,digit,segment)
                posed_segments[key]=_segment_endpoints(posed,finger_indices,rig_evidence["tip_local_offsets"],side,digit,segment)
    joint_to_segment={finger_indices[f"{side}_finger{digit}_{segment}"]:(side,digit,segment) for side in ("left","right") for digit in range(1,6) for segment in range(1,4)}
    lbs_radial_error=[];dqs_radial_error=[];samples=0
    for index in sorted(finger_vertices):
        active=[(weight,joint) for joint,weight in zip(weights.joints[index],weights.weights[index]) if joint in joint_to_segment and weight>1e-9]
        if not active:continue
        _weight,joint=max(active)
        key=joint_to_segment[joint]
        bind_radius,_=_segment_distance(body.vertices[index],*bind_segments[key])
        if bind_radius<0.001:continue
        lbs_radius,_=_segment_distance(lbs_mesh.vertices[index],*posed_segments[key])
        dqs_radius,_=_segment_distance(dqs_mesh.vertices[index],*posed_segments[key])
        lbs_radial_error.append(abs(lbs_radius-bind_radius))
        dqs_radial_error.append(abs(dqs_radius-bind_radius))
        samples+=1
    if not samples:raise ValueError("no radial-preservation samples")
    lbs_mean=sum(lbs_radial_error)/samples;dqs_mean=sum(dqs_radial_error)/samples

    rifle=sentinel_rifle_human_scale();translation=tuple(float(v) for v in v07["weapon"]["translation"]);rotation=_quat(v07["weapon"]["rotation"])
    component_for_side={"right":"primary_grip","left":"foregrip"}
    side_by_joint={joint:side for side in ("left","right") for digit in range(1,6) for segment in range(1,4) for joint in [finger_indices[f"{side}_finger{digit}_{segment}"]]}
    lbs_pen=[];dqs_pen=[]
    for index in sorted(finger_vertices):
        active=[(weight,joint) for joint,weight in zip(weights.joints[index],weights.weights[index]) if joint in side_by_joint and weight>1e-9]
        if not active:continue
        _weight,joint=max(active);side=side_by_joint[joint]
        lo,hi=bounds(rifle.components[component_for_side[side]])
        lbs_local=_world_to_weapon_local(lbs_mesh.vertices[index],translation,rotation)
        dqs_local=_world_to_weapon_local(dqs_mesh.vertices[index],translation,rotation)
        lbs_pen.append(max(0.0,-_aabb_sdf(lbs_local,lo,hi)))
        dqs_pen.append(max(0.0,-_aabb_sdf(dqs_local,lo,hi)))

    evidence={
        "schema":SCHEMA,
        "source_pose_schema":v07["schema"],
        "pose_reconstruction_max_error_m":reconstruction_error,
        "finger_vertex_count":len(finger_vertices),
        "nonfinger_max_delta_from_v0_7_lbs_m":nonfinger_max,
        "finger_lbs_to_dqs_delta_m":{"mean":sum(finger_delta)/len(finger_delta),"max":max(finger_delta)},
        "radial_preservation":{"samples":samples,"lbs_mean_abs_error_m":lbs_mean,"dqs_mean_abs_error_m":dqs_mean,"relative_error":dqs_mean/max(lbs_mean,1e-12)},
        "grip_aabb_surface_penetration":{"lbs_max_m":max(lbs_pen,default=0.0),"dqs_max_m":max(dqs_pen,default=0.0)},
        "contact_summary":v07["contact_summary"],
        "finger_rig":rig_evidence,
        "finger_skin":skin_evidence,
        "truth":{
            "same_v0_7_skeleton_pose":True,
            "same_v0_7_weights":True,
            "same_weapon_and_palm_surface_contact":True,
            "dqs_applied_only_to_finger_influenced_vertices":True,
            "production_deformation_claim":False,
            "automatic_visual_promotion":False,
            "notes":[
                "The reconstructed LBS pose must match v0.7 before DQS is evaluated, preventing a hidden pose/contact change from contaminating the comparison.",
                "Only vertices with an appended finger-joint influence use DQS. All other character vertices stay exactly on the v0.7 LBS result.",
                "Radial preservation is a technical volume-retention metric around the source-grounded finger segments; Godot close views still decide whether knuckles actually look better."
            ],
        },
    }
    return dqs_mesh,evidence


def build_preferred_grip_dqs_pose():
    body,_uv,_state=_load_identity_body();return build_grip_dqs_pose(body)


if __name__=="__main__":
    import json
    mesh,evidence=build_preferred_grip_dqs_pose();print(json.dumps({"vertices":len(mesh.vertices),"faces":len(mesh.faces),**evidence},indent=2))
