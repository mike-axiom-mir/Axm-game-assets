#!/usr/bin/env python3
"""Rifle contact v0.8: align the palm plane before physical finger wrap.

v0.7 moved each palm socket from the old component center to the real near grip
surface, but its retained diagnostic proved the source-grounded palm plane was
still about 70-73 degrees edge-on to the grip face. Several straight fingertips
therefore already crossed the weapon volume and no safe middle-finger curl
existed.

v0.8 keeps the rifle world transform fixed and performs a two-pass arm solve:
1. solve the palm socket to the real near surface;
2. derive the palm plane from source-grounded proximal finger roots;
3. apply the smallest world-space hand-orientation correction that maps that
   palm normal onto the grip's inward radial direction;
4. re-solve the same shoulder/elbow/wrist chain to the same surface contact;
5. wrap each finger toward the far grip surface with the existing penetration
   budget.

Geometry metrics are proposal evidence only. Godot hand-close evidence remains
the visual promotion boundary.
"""
from __future__ import annotations

import copy
from dataclasses import replace
from math import acos, degrees

from native_geometry import Mesh, bounds
from native_hm08_humanoid_rig import derive_hm08_rig_landmarks
from native_hm08_rifle_contact_pose import _distance, _quat_from_to, _quat_mul
from native_hm08_rifle_contact_pose_v2 import _joint_target_for_contact, _solve_arm_rotations, derive_shared_rig_arms
from native_hm08_rifle_contact_pose_v5 import SCALE_CANDIDATES, _reconstruct_v4_on_finger_rig, _solve_digit, _tip_world
from native_hm08_rifle_contact_pose_v6 import (
    MAX_TIP_PENETRATION_M,
    SURFACE_CLEARANCE_M,
    _dot,
    _grip_volume,
    _mul,
    _normalize,
    _sub,
    _surface_gap,
    _surface_target,
)
from native_hm08_rifle_contact_pose_v7 import PALM_SURFACE_CLEARANCE_M, _near_surface_palm_target
from native_hm08_undersuit import _load_identity_body
from native_skin import Skeleton, global_joint_matrices, skin_vertices, transform_point, validate_skeleton
from native_weapon_human_scale import sentinel_rifle_human_scale

SCHEMA = "axm.game-assets.hm08-rifle-contact-pose.v0.8"
MAX_FINAL_PALM_NORMAL_ERROR_DEG = 2.0
MAX_PALM_CORRECTION_DEG = 95.0
MAX_ROOT_PENETRATION_M = 0.004


def _add(a,b):
    return a[0]+b[0],a[1]+b[1],a[2]+b[2]


def _cross(a,b):
    return (a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0])


def _mean(points):
    inv=1.0/len(points)
    return tuple(sum(point[axis] for point in points)*inv for axis in range(3))


def _angle_deg(a,b):
    dot=max(-1.0,min(1.0,_dot(_normalize(a),_normalize(b))))
    return degrees(acos(dot))


def _palm_plane_normal_world(skeleton: Skeleton, indices: dict[str,int], side: str, inward_hint):
    matrices=global_joint_matrices(skeleton)
    hand_index=indices[f"{side}_hand"]
    hand=(matrices[hand_index][0][3],matrices[hand_index][1][3],matrices[hand_index][2][3])
    roots=[]
    for digit in range(2,6):
        index=indices[f"{side}_finger{digit}_1"]
        roots.append((matrices[index][0][3],matrices[index][1][3],matrices[index][2][3]))
    knuckle_center=_mean(roots)
    spread=_sub(roots[-1],roots[0])
    wrist_to_knuckles=_sub(knuckle_center,hand)
    normal=_normalize(_cross(spread,wrist_to_knuckles))
    inward=_normalize(inward_hint)
    if _dot(normal,inward)<0.0:
        normal=_mul(normal,-1.0)
    return normal,knuckle_center,hand


def _solve_arm_to_surface_with_palm_alignment(
    joints,
    bind: Skeleton,
    indices: dict[str,int],
    arms,
    v4_globals,
    rifle,
    volume,
    weapon_rotation,
    side: str,
    sign: float,
    socket_key: str,
    old_center_contact,
):
    arm=arms[side]
    hand_index=indices[f"{side}_hand"]
    hand_joint_before=(v4_globals[hand_index][0][3],v4_globals[hand_index][1][3],v4_globals[hand_index][2][3])
    surface_target,target_evidence=_near_surface_palm_target(volume,old_center_contact,hand_joint_before)
    outward=tuple(float(value) for value in target_evidence["near_surface_direction"])
    inward=_mul(outward,-1.0)
    initial_desired=_quat_mul(weapon_rotation,rifle.sockets[socket_key].rotation)

    # First pass reproduces v0.7's physically located but edge-on palm.
    first_joint_target=_joint_target_for_contact(surface_target,arm.hand_socket,initial_desired)
    first_reach=_distance(arm.shoulder,first_joint_target)
    maximum=arm.upper_length_m+arm.forearm_hand_length_m
    if first_reach>maximum+1e-9:
        raise ValueError(f"{side} first-pass palm target outside reach: {first_reach} > {maximum}")
    elbow,sr,er,hr=_solve_arm_rotations(arm,first_joint_target,initial_desired,sign=sign)
    provisional=list(joints)
    for suffix,rotation in (("upper_arm",sr),("forearm",er),("hand",hr)):
        index=indices[f"{side}_{suffix}"]
        provisional[index]=replace(provisional[index],rotation=rotation)
    first_skeleton=Skeleton(provisional)
    if validate_skeleton(first_skeleton)["status"]!="pass":
        raise ValueError(f"{side} first-pass surface skeleton invalid")
    first_normal,first_knuckle_center,_first_hand=_palm_plane_normal_world(first_skeleton,indices,side,inward)
    initial_normal_error=_angle_deg(first_normal,inward)

    correction=_quat_from_to(first_normal,inward)
    corrected_desired=_quat_mul(correction,initial_desired)
    correction_angle=_angle_deg(first_normal,inward)
    if correction_angle>MAX_PALM_CORRECTION_DEG:
        raise ValueError(f"{side} palm correction implausibly large: {correction_angle} deg")

    # Second pass keeps the exact same palm surface target but changes the hand
    # world orientation so the physical palm plane faces the grip.
    joint_target=_joint_target_for_contact(surface_target,arm.hand_socket,corrected_desired)
    reach=_distance(arm.shoulder,joint_target)
    if reach>maximum+1e-9:
        raise ValueError(f"{side} aligned palm target outside reach: {reach} > {maximum}")
    elbow,shoulder_rotation,elbow_rotation,hand_rotation=_solve_arm_rotations(
        arm,joint_target,corrected_desired,sign=sign
    )
    for suffix,rotation in (("upper_arm",shoulder_rotation),("forearm",elbow_rotation),("hand",hand_rotation)):
        index=indices[f"{side}_{suffix}"]
        joints[index]=replace(joints[index],rotation=rotation)

    row={
        "weapon_component":volume["name"],
        "old_center_contact_world":list(old_center_contact),
        "physical_palm_target":target_evidence,
        "inward_grip_direction_world":list(inward),
        "first_pass":{
            "joint_target":list(first_joint_target),
            "reach_m":first_reach,
            "palm_plane_normal_world":list(first_normal),
            "palm_normal_error_deg":initial_normal_error,
            "knuckle_center_world":list(first_knuckle_center),
        },
        "orientation_correction":{
            "world_quaternion":list(correction),
            "angle_deg":correction_angle,
            "rule":"shortest_world_rotation_from_source_grounded_palm_plane_normal_to_grip_inward_radial_direction",
        },
        "final_joint_target":list(joint_target),
        "reach_m":reach,
        "maximum_reach_m":maximum,
        "elbow":list(elbow),
        "shoulder_rotation":list(shoulder_rotation),
        "elbow_rotation":list(elbow_rotation),
        "hand_rotation":list(hand_rotation),
        "desired_hand_world_rotation":list(corrected_desired),
    }
    return joints,row


def build_palm_aligned_rifle_contact_pose(body_m: Mesh) -> tuple[Mesh,dict[str,object]]:
    (
        _v4_mesh,v4,bind,weights,indices,rig_evidence,skin_evidence,v4_open_skeleton,_v4_open_mesh,_arm_rotation_exact
    )=_reconstruct_v4_on_finger_rig(body_m)
    rifle=sentinel_rifle_human_scale()
    weapon_rotation=tuple(float(value) for value in v4["weapon"]["rotation"])
    weapon_translation=tuple(float(value) for value in v4["weapon"]["translation"])
    volumes={
        "right":_grip_volume(rifle.components["primary_grip"],weapon_rotation,weapon_translation,name="primary_grip"),
        "left":_grip_volume(rifle.components["foregrip"],weapon_rotation,weapon_translation,name="foregrip"),
    }
    landmarks=derive_hm08_rig_landmarks(body_m)
    arms=derive_shared_rig_arms(body_m,landmarks)
    v4_globals=global_joint_matrices(v4_open_skeleton)
    joints=list(bind.joints)
    surface_rows={}
    for side,sign,socket_key,contact_key in (
        ("right",1.0,"primary_grip","primary_hand_contact_world_position"),
        ("left",-1.0,"support_grip","support_hand_contact_world_position"),
    ):
        old_center=tuple(float(value) for value in v4["contact"][contact_key])
        joints,row=_solve_arm_to_surface_with_palm_alignment(
            joints,bind,indices,arms,v4_globals,rifle,volumes[side],weapon_rotation,
            side,sign,socket_key,old_center
        )
        surface_rows[side]=row

    aligned_skeleton=Skeleton(joints)
    aligned_report=validate_skeleton(aligned_skeleton)
    if aligned_report["status"]!="pass":
        raise ValueError(f"palm-aligned skeleton invalid: {aligned_report}")
    aligned_globals=global_joint_matrices(aligned_skeleton)
    aligned_open_mesh=Mesh(
        "sentinel_hm08_palm_aligned_open_fingers_v0_8",
        skin_vertices(body_m,weights,bind,aligned_skeleton),
        list(body_m.faces),
    )

    palm_errors=[];palm_gaps=[];old_center_separations=[];final_normal_errors=[];root_gaps=[]
    for side,contact_key in (("right","primary_hand_contact_world_position"),("left","support_hand_contact_world_position")):
        arm=arms[side]
        hand_matrix=aligned_globals[indices[f"{side}_hand"]]
        palm_world=transform_point(hand_matrix,arm.hand_socket.position)
        target=tuple(float(value) for value in surface_rows[side]["physical_palm_target"]["surface_target_world"])
        old_center=tuple(float(value) for value in v4["contact"][contact_key])
        inward=tuple(float(value) for value in surface_rows[side]["inward_grip_direction_world"])
        normal,knuckle_center,hand_world=_palm_plane_normal_world(aligned_skeleton,indices,side,inward)
        normal_error=_angle_deg(normal,inward)
        palm_error=_distance(palm_world,target)
        gap=_surface_gap(volumes[side],palm_world)
        separation=_distance(palm_world,old_center)
        side_root_gaps={}
        for digit in range(1,6):
            index=indices[f"{side}_finger{digit}_1"]
            root=(aligned_globals[index][0][3],aligned_globals[index][1][3],aligned_globals[index][2][3])
            root_gap=_surface_gap(volumes[side],root)
            root_gaps.append(float(root_gap["surface_gap_m"]))
            side_root_gaps[str(digit)]={"world":list(root),"surface_gap":root_gap}
        palm_errors.append(palm_error);palm_gaps.append(float(gap["surface_gap_m"]));old_center_separations.append(separation);final_normal_errors.append(normal_error)
        surface_rows[side].update({
            "resolved_palm_socket_world":list(palm_world),
            "surface_target_error_m":palm_error,
            "old_center_socket_separation_m":separation,
            "resolved_palm_surface_gap":gap,
            "final_palm_plane_normal_world":list(normal),
            "final_palm_normal_error_deg":normal_error,
            "final_knuckle_center_world":list(knuckle_center),
            "final_hand_joint_world":list(hand_world),
            "proximal_finger_roots":side_root_gaps,
        })

    # Wrap digits only after the palm plane is aligned.
    open_globals=aligned_globals
    current=aligned_skeleton
    choices={};improvements=[];final_gaps=[]
    for side in ("right","left"):
        volume=volumes[side]
        side_rows={
            "volume":{
                "name":volume["name"],
                "center_world":list(volume["center"]),
                "principal_axis_world":list(volume["axis"]),
                "axial_range_m":[volume["t_min"],volume["t_max"]],
                "axial_span_m":volume["span"],
                "max_radial_extent_m":volume["max_radius"],
            },
            "digits":{},
        }
        for digit in range(1,6):
            root_index=indices[f"{side}_finger{digit}_1"]
            root_world=(open_globals[root_index][0][3],open_globals[root_index][1][3],open_globals[root_index][2][3])
            open_tip=_tip_world(current,indices,rig_evidence,side,digit)
            target,target_meta=_surface_target(volume,root_world,open_tip)
            open_error=_distance(open_tip,target)
            candidates=[]
            for scale in SCALE_CANDIDATES:
                candidate,segments=_solve_digit(current,bind,indices,rig_evidence,side,digit,target,scale)
                tip=_tip_world(candidate,indices,rig_evidence,side,digit)
                error=_distance(tip,target)
                gap=_surface_gap(volume,tip)
                penetration=max(0.0,-float(gap["surface_gap_m"]))
                safe=penetration<=MAX_TIP_PENETRATION_M+1e-12
                candidates.append((0 if safe else 1,error,penetration,scale,candidate,tip,segments,gap))
            candidates.sort(key=lambda row:(row[0],row[1],row[2],row[3]))
            safe_count=sum(1 for row in candidates if row[0]==0)
            if safe_count<=0:
                raise ValueError(f"no collision-safe v0.8 finger candidate for {side} digit {digit}: {[(row[1],row[2],row[3]) for row in candidates]}")
            _unsafe,error,penetration,scale,current,tip,segments,gap=candidates[0]
            improvement=open_error-error
            improvements.append(improvement);final_gaps.append(float(gap["surface_gap_m"]))
            side_rows["digits"][str(digit)]={
                "root_world":list(root_world),
                "open_tip_world":list(open_tip),
                "target":target_meta,
                "scale":scale,
                "safe_candidate_count":safe_count,
                "selected_tip_penetration_m":penetration,
                "open_tip_to_surface_target_m":open_error,
                "curled_tip_to_surface_target_m":error,
                "improvement_m":improvement,
                "curled_tip_world":list(tip),
                "final_grip_surface_gap":gap,
                "segments":segments,
            }
        open_values=[row["open_tip_to_surface_target_m"] for row in side_rows["digits"].values()]
        curled_values=[row["curled_tip_to_surface_target_m"] for row in side_rows["digits"].values()]
        side_rows["open_target_mean_m"]=sum(open_values)/len(open_values)
        side_rows["curled_target_mean_m"]=sum(curled_values)/len(curled_values)
        side_rows["mean_improvement_m"]=side_rows["open_target_mean_m"]-side_rows["curled_target_mean_m"]
        choices[side]=side_rows

    posed=current
    posed_report=validate_skeleton(posed)
    if posed_report["status"]!="pass":
        raise ValueError(f"v0.8 posed skeleton invalid: {posed_report}")
    posed_mesh=Mesh("sentinel_hm08_palm_aligned_grip_v0_8",skin_vertices(body_m,weights,bind,posed),list(body_m.faces))

    finger_joint_set=set(rig_evidence["finger_indices"].values())
    curl_moved=0;finger_curl_max=0.0;nonfinger_curl_max=0.0
    for index,(before,after) in enumerate(zip(aligned_open_mesh.vertices,posed_mesh.vertices)):
        delta=_distance(before,after)
        active=any(joint in finger_joint_set and weight>1e-9 for joint,weight in zip(weights.joints[index],weights.weights[index]))
        if active:
            if delta>1e-10:curl_moved+=1
            finger_curl_max=max(finger_curl_max,delta)
        else:
            nonfinger_curl_max=max(nonfinger_curl_max,delta)

    lo,hi=bounds(body_m);height=hi[1]-lo[1]
    head_indices=[i for i,p in enumerate(body_m.vertices) if p[1]>=lo[1]+height*0.84]
    lower_indices=[i for i,p in enumerate(body_m.vertices) if p[1]<=lo[1]+height*0.50]
    head_surface=max(_distance(body_m.vertices[i],aligned_open_mesh.vertices[i]) for i in head_indices)
    lower_surface=max(_distance(body_m.vertices[i],aligned_open_mesh.vertices[i]) for i in lower_indices)
    head_curl=max(_distance(aligned_open_mesh.vertices[i],posed_mesh.vertices[i]) for i in head_indices)
    lower_curl=max(_distance(aligned_open_mesh.vertices[i],posed_mesh.vertices[i]) for i in lower_indices)
    skin_preserved=(
        skin_evidence["preserved_nonfinger_rows"]==skin_evidence["expected_preserved_nonfinger_rows"]
        and skin_evidence["truth"]["shared_body_skin_preserved_outside_fingers"] is True
    )
    min_improvement=min(improvements)
    max_tip_penetration=max(0.0,-min(final_gaps))
    max_root_penetration=max(0.0,-min(root_gaps))

    acceptance={
        "finger_rig_53_joints":len(bind.joints)==53 and rig_evidence["finger_joint_count"]==30,
        "finger_skin_green":skin_evidence["validation"]["status"]=="pass" and skin_evidence["minimum_vertices_per_segment"]>=3,
        "finger_skin_preserves_nonfinger_v2_rows":skin_preserved,
        "human_scale_rifle_transform_preserved":v4["weapon"]["scale"]==[1.0,1.0,1.0],
        "physical_palm_targets_exact":max(palm_errors)<1e-8,
        "palms_moved_off_center_sockets":min(old_center_separations)>0.020,
        "palms_on_near_grip_surface":all(abs(gap-PALM_SURFACE_CLEARANCE_M)<0.008 for gap in palm_gaps),
        "palm_plane_aligned_to_grip":max(final_normal_errors)<=MAX_FINAL_PALM_NORMAL_ERROR_DEG,
        "orientation_correction_bounded":max(float(surface_rows[side]["orientation_correction"]["angle_deg"]) for side in ("right","left"))<=MAX_PALM_CORRECTION_DEG,
        "proximal_roots_not_deep_inside_grip":max_root_penetration<=MAX_ROOT_PENETRATION_M,
        "surface_arm_targets_reachable":all(surface_rows[side]["reach_m"]<=surface_rows[side]["maximum_reach_m"]+1e-9 for side in ("right","left")),
        "every_fingertip_closer_to_far_surface":len(improvements)==10 and min_improvement>1e-6,
        "both_hand_target_means_closer":all(choices[side]["curled_target_mean_m"]<choices[side]["open_target_mean_m"] for side in ("right","left")),
        "tip_penetration_bounded":max_tip_penetration<=MAX_TIP_PENETRATION_M+1e-12,
        "finger_surface_moves":curl_moved>200 and finger_curl_max>0.003,
        "nonfinger_rows_stationary_under_finger_curl":nonfinger_curl_max<1e-8,
        "head_unchanged_by_surface_arm_resolve":head_surface<1e-9,
        "lower_body_unchanged_by_surface_arm_resolve":lower_surface<1e-9,
        "head_unchanged_by_finger_curl":head_curl<1e-9,
        "lower_body_unchanged_by_finger_curl":lower_curl<1e-9,
        "curl_bounded":finger_curl_max<0.12,
        "posed_skeleton_valid":posed_report["status"]=="pass",
    }

    result=copy.deepcopy(v4)
    result["schema"]=SCHEMA
    result["pose_id"]="cross_chest_palm_plane_aligned_physical_grip_v0.8"
    result["weapon"]["scale"]=[1.0,1.0,1.0]
    result["surface_palm_contact"]={
        "changed_variable_from_v0_7":"wrist_world_orientation_align_source_grounded_palm_plane_to_grip_inward_normal",
        "palm_surface_clearance_m":PALM_SURFACE_CLEARANCE_M,
        "rows":surface_rows,
        "maximum_target_error_m":max(palm_errors),
        "old_center_socket_separation_m_range":[min(old_center_separations),max(old_center_separations)],
        "resolved_palm_surface_gap_m_range":[min(palm_gaps),max(palm_gaps)],
        "first_pass_palm_normal_error_deg_range":[min(float(surface_rows[s]["first_pass"]["palm_normal_error_deg"]) for s in ("right","left")),max(float(surface_rows[s]["first_pass"]["palm_normal_error_deg"]) for s in ("right","left"))],
        "final_palm_normal_error_deg_range":[min(final_normal_errors),max(final_normal_errors)],
        "orientation_correction_deg_range":[min(float(surface_rows[s]["orientation_correction"]["angle_deg"]) for s in ("right","left")),max(float(surface_rows[s]["orientation_correction"]["angle_deg"]) for s in ("right","left"))],
        "proximal_root_surface_gap_m_range":[min(root_gaps),max(root_gaps)],
        "max_proximal_root_penetration_m":max_root_penetration,
    }
    result["shared_rig"]={
        "schema":rig_evidence["schema"],
        "joint_count":len(bind.joints),
        "finger_joint_count":rig_evidence["finger_joint_count"],
        "finger_indices":rig_evidence["finger_indices"],
        "finger_rig_evidence":rig_evidence,
        "finger_skin_evidence":skin_evidence,
    }
    result["finger_grip"]={
        "changed_variable_from_v0_7":"palm_plane_alignment_before_collision_bounded_far_surface_finger_wrap",
        "v0_5_visual_status":"rejected_real_godot_hand_close_crushed_twisted_fingers",
        "v0_6_native_status":"rejected_no_collision_safe_pinky_candidate_from_center_socket_palm_state",
        "v0_7_native_status":"rejected_palm_surface_position_correct_but_palm_plane_about_70_to_73_degrees_edge_on",
        "selection_rule":"align source-grounded palm plane to grip inward normal at fixed palm surface contact, then use collision-bounded per-digit far-surface targets",
        "surface_clearance_m":SURFACE_CLEARANCE_M,
        "maximum_tip_penetration_m":MAX_TIP_PENETRATION_M,
        "scale_candidates":list(SCALE_CANDIDATES),
        "choices":choices,
        "minimum_target_improvement_m":min_improvement,
        "mean_target_improvement_m":sum(improvements)/len(improvements),
        "final_tip_surface_gap_m_range":[min(final_gaps),max(final_gaps)],
        "max_deep_tip_penetration_m":max_tip_penetration,
        "curl_moved_finger_vertices":curl_moved,
        "finger_curl_max_displacement_m":finger_curl_max,
        "nonfinger_curl_max_displacement_m":nonfinger_curl_max,
    }
    result["acceptance"]=acceptance
    result["truth"]={
        "uses_shared_full_body_rig":True,
        "source_grounded_finger_chains":True,
        "source_grounded_palm_plane":True,
        "human_scale_rifle_world_transform_preserved":True,
        "real_weapon_grip_volumes_used":True,
        "v0_5_visual_result_promoted":False,
        "v0_6_native_result_promoted":False,
        "v0_7_native_result_promoted":False,
        "production_grip_claim":False,
        "automatic_visual_promotion":False,
        "notes":[
            "v0.8 is the first grip attempt that treats palm position and palm orientation as separate physical constraints.",
            "The first v0.8 pass intentionally reproduces v0.7, measures the source-grounded palm plane, then applies the smallest world-space correction needed to face the grip before re-solving the arm.",
            "The rifle is neither moved nor scaled during this repair. Shoulder/elbow/wrist state changes only to satisfy the new physical palm surface position plus palm-plane orientation.",
            "Finger curl remains bounded and collision-aware against the real primary-grip/foregrip volumes.",
            "Native geometry can reject impossible contact, but only the preserved Godot hand-close camera may promote visual grip quality."
        ],
    }
    if not all(acceptance.values()):
        raise ValueError(f"v0.8 palm-aligned grip acceptance failed: {acceptance}; palm={result['surface_palm_contact']}; finger={result['finger_grip']}")
    return posed_mesh,result


def build_preferred_palm_aligned_rifle_contact_pose():
    body,_uv,_state=_load_identity_body()
    return build_palm_aligned_rifle_contact_pose(body)


if __name__=="__main__":
    import json
    mesh,packet=build_preferred_palm_aligned_rifle_contact_pose()
    print(json.dumps({"vertices":len(mesh.vertices),"faces":len(mesh.faces),"acceptance":packet["acceptance"],"surface_palm_contact":packet["surface_palm_contact"],"finger_grip":packet["finger_grip"]},indent=2))
