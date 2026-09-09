#!/usr/bin/env python3
"""Rifle contact v0.7: physical palm-surface contact + finger wrap.

v0.4 proved exact abstract palm-socket to weapon-socket contact. v0.5 then
proved finger articulation but real Godot rejected socket-center convergence.
v0.6 targeted real grip surfaces, but its collision gate proved the deeper
problem: the v0.4 palm itself starts inside the grip volume, leaving no safe
finger-only solution for at least the primary-hand pinky.

v0.7 keeps the human-scale rifle world transform fixed. It reinterprets the
hand contact physically: each existing palm socket is moved from the weapon
socket center to the near surface of the actual primary-grip / foregrip mesh,
the shared arms are re-solved to those surface contacts, and only then do the
source-grounded finger chains wrap toward far-surface targets.
"""
from __future__ import annotations

import copy
from dataclasses import replace

from native_geometry import Mesh, bounds
from native_hm08_humanoid_rig import derive_hm08_rig_landmarks
from native_hm08_rifle_contact_pose import _distance, _quat_mul
from native_hm08_rifle_contact_pose_v2 import (
    _joint_target_for_contact,
    _solve_arm_rotations,
    derive_shared_rig_arms,
)
from native_hm08_rifle_contact_pose_v5 import SCALE_CANDIDATES, _reconstruct_v4_on_finger_rig, _solve_digit, _tip_world
from native_hm08_rifle_contact_pose_v6 import (
    AXIAL_MARGIN_FRACTION,
    MAX_TIP_PENETRATION_M,
    SURFACE_CLEARANCE_M,
    _clamp,
    _dot,
    _grip_volume,
    _mul,
    _normalize,
    _sub,
    _surface_gap,
    _surface_target,
)
from native_hm08_undersuit import _load_identity_body
from native_skin import Skeleton, global_joint_matrices, skin_vertices, transform_point, validate_skeleton
from native_weapon_human_scale import sentinel_rifle_human_scale

SCHEMA = "axm.game-assets.hm08-rifle-contact-pose.v0.7"
PALM_SURFACE_CLEARANCE_M = 0.004


def _add(a,b):
    return a[0]+b[0],a[1]+b[1],a[2]+b[2]


def _near_surface_palm_target(volume: dict[str,object], center_socket_world, hand_joint_world):
    center=volume["center"];axis=volume["axis"]
    assert isinstance(center,tuple) and isinstance(axis,tuple)
    t_raw=_dot(_sub(center_socket_world,center),axis)
    margin=float(volume["span"])*AXIAL_MARGIN_FRACTION
    t=_clamp(t_raw,float(volume["t_min"])+margin,float(volume["t_max"])-margin)
    centerline=_add(center,_mul(axis,t))
    radial=_sub(hand_joint_world,centerline)
    radial=_sub(radial,_mul(axis,_dot(radial,axis)))
    near_direction=_normalize(radial)
    support=max(_dot(row,near_direction) for row in volume["radial_rows"])
    target=_add(centerline,_mul(near_direction,support+PALM_SURFACE_CLEARANCE_M))
    return target,{
        "center_socket_world":list(center_socket_world),
        "hand_joint_world_before_surface_resolve":list(hand_joint_world),
        "socket_axial_projection_m":t_raw,
        "target_axial_projection_m":t,
        "near_surface_direction":list(near_direction),
        "support_radius_m":support,
        "surface_clearance_m":PALM_SURFACE_CLEARANCE_M,
        "surface_target_world":list(target),
        "center_to_surface_shift_m":_distance(center_socket_world,target),
    }


def build_physical_grip_rifle_contact_pose(body_m: Mesh) -> tuple[Mesh,dict[str,object]]:
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
        arm=arms[side]
        hand_index=indices[f"{side}_hand"]
        hand_joint_world=(v4_globals[hand_index][0][3],v4_globals[hand_index][1][3],v4_globals[hand_index][2][3])
        old_center_contact=tuple(float(value) for value in v4["contact"][contact_key])
        surface_target,target_evidence=_near_surface_palm_target(volumes[side],old_center_contact,hand_joint_world)
        desired_hand_rotation=_quat_mul(weapon_rotation,rifle.sockets[socket_key].rotation)
        joint_target=_joint_target_for_contact(surface_target,arm.hand_socket,desired_hand_rotation)
        reach=_distance(arm.shoulder,joint_target)
        maximum=arm.upper_length_m+arm.forearm_hand_length_m
        if reach>maximum+1e-9:
            raise ValueError(f"{side} physical palm surface target outside reach: {reach} > {maximum}")
        elbow,shoulder_rotation,elbow_rotation,hand_rotation=_solve_arm_rotations(
            arm,joint_target,desired_hand_rotation,sign=sign
        )
        for suffix,rotation in (
            ("upper_arm",shoulder_rotation),
            ("forearm",elbow_rotation),
            ("hand",hand_rotation),
        ):
            index=indices[f"{side}_{suffix}"]
            source=joints[index]
            joints[index]=replace(source,rotation=rotation)
        surface_rows[side]={
            "weapon_component":volumes[side]["name"],
            "old_center_contact_world":list(old_center_contact),
            "physical_palm_target":target_evidence,
            "joint_target":list(joint_target),
            "reach_m":reach,
            "maximum_reach_m":maximum,
            "elbow":list(elbow),
            "shoulder_rotation":list(shoulder_rotation),
            "elbow_rotation":list(elbow_rotation),
            "hand_rotation":list(hand_rotation),
        }

    surface_skeleton=Skeleton(joints)
    surface_report=validate_skeleton(surface_skeleton)
    if surface_report["status"]!="pass":
        raise ValueError(f"physical palm surface skeleton invalid: {surface_report}")
    surface_globals=global_joint_matrices(surface_skeleton)
    surface_open_mesh=Mesh(
        "sentinel_hm08_physical_palm_surface_open_fingers_v0_7",
        skin_vertices(body_m,weights,bind,surface_skeleton),
        list(body_m.faces),
    )

    palm_errors=[]
    old_center_separations=[]
    palm_surface_gaps=[]
    for side,contact_key in (("right","primary_hand_contact_world_position"),("left","support_hand_contact_world_position")):
        arm=arms[side]
        hand_matrix=surface_globals[indices[f"{side}_hand"]]
        palm_world=transform_point(hand_matrix,arm.hand_socket.position)
        target=tuple(float(value) for value in surface_rows[side]["physical_palm_target"]["surface_target_world"])
        old_center=tuple(float(value) for value in v4["contact"][contact_key])
        error=_distance(palm_world,target)
        old_separation=_distance(palm_world,old_center)
        gap=_surface_gap(volumes[side],palm_world)
        palm_errors.append(error);old_center_separations.append(old_separation);palm_surface_gaps.append(float(gap["surface_gap_m"]))
        surface_rows[side]["resolved_palm_socket_world"]=list(palm_world)
        surface_rows[side]["surface_target_error_m"]=error
        surface_rows[side]["old_center_socket_separation_m"]=old_separation
        surface_rows[side]["resolved_palm_surface_gap"]=gap

    # With the palm now on the near surface, solve each finger toward the far
    # surface using the same collision-aware candidate policy v0.6 introduced.
    open_globals=surface_globals
    current=surface_skeleton
    choices={}
    improvements=[]
    final_gaps=[]
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
                target_error=_distance(tip,target)
                gap=_surface_gap(volume,tip)
                penetration=max(0.0,-float(gap["surface_gap_m"]))
                safe=penetration<=MAX_TIP_PENETRATION_M+1e-12
                candidates.append((0 if safe else 1,target_error,penetration,scale,candidate,tip,segments,gap))
            candidates.sort(key=lambda row:(row[0],row[1],row[2],row[3]))
            safe_count=sum(1 for row in candidates if row[0]==0)
            if safe_count<=0:
                raise ValueError(f"no collision-safe v0.7 finger candidate for {side} digit {digit}: {[(row[1],row[2],row[3]) for row in candidates]}")
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
        raise ValueError(f"v0.7 posed skeleton invalid: {posed_report}")
    posed_mesh=Mesh(
        "sentinel_hm08_physical_grip_rifle_contact_v0_7",
        skin_vertices(body_m,weights,bind,posed),
        list(body_m.faces),
    )

    finger_joint_set=set(rig_evidence["finger_indices"].values())
    curl_moved=0;finger_curl_max=0.0;nonfinger_curl_max=0.0
    for index,(before,after) in enumerate(zip(surface_open_mesh.vertices,posed_mesh.vertices)):
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
    head_surface=max(_distance(body_m.vertices[i],surface_open_mesh.vertices[i]) for i in head_indices)
    lower_surface=max(_distance(body_m.vertices[i],surface_open_mesh.vertices[i]) for i in lower_indices)
    head_curl=max(_distance(surface_open_mesh.vertices[i],posed_mesh.vertices[i]) for i in head_indices)
    lower_curl=max(_distance(surface_open_mesh.vertices[i],posed_mesh.vertices[i]) for i in lower_indices)
    skin_preserved=(
        skin_evidence["preserved_nonfinger_rows"]==skin_evidence["expected_preserved_nonfinger_rows"]
        and skin_evidence["truth"]["shared_body_skin_preserved_outside_fingers"] is True
    )
    max_tip_penetration=max(0.0,-min(final_gaps))
    min_improvement=min(improvements)

    acceptance={
        "finger_rig_53_joints":len(bind.joints)==53 and rig_evidence["finger_joint_count"]==30,
        "finger_skin_green":skin_evidence["validation"]["status"]=="pass" and skin_evidence["minimum_vertices_per_segment"]>=3,
        "finger_skin_preserves_nonfinger_v2_rows":skin_preserved,
        "human_scale_rifle_transform_preserved":v4["weapon"]["scale"]==[1.0,1.0,1.0],
        "physical_palm_targets_exact":max(palm_errors)<1e-8,
        "palms_moved_off_center_sockets":min(old_center_separations)>0.020,
        "palms_on_near_grip_surface":all(abs(gap-PALM_SURFACE_CLEARANCE_M)<0.008 for gap in palm_surface_gaps),
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
    result["pose_id"]="cross_chest_physical_palm_surface_grip_v0.7"
    result["weapon"]["scale"]=[1.0,1.0,1.0]
    result["surface_palm_contact"]={
        "changed_variable_from_v0_4":"hand_contact_semantics_center_socket_to_near_physical_grip_surface",
        "palm_surface_clearance_m":PALM_SURFACE_CLEARANCE_M,
        "rows":surface_rows,
        "maximum_target_error_m":max(palm_errors),
        "old_center_socket_separation_m_range":[min(old_center_separations),max(old_center_separations)],
        "resolved_palm_surface_gap_m_range":[min(palm_surface_gaps),max(palm_surface_gaps)],
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
        "changed_variable_from_v0_6":"palm_start_state_center_socket_to_physical_near_surface_before_same_far_surface_finger_objective",
        "v0_5_visual_status":"rejected_real_godot_hand_close_crushed_twisted_fingers",
        "v0_6_native_status":"rejected_no_collision_safe_pinky_candidate_from_center_socket_palm_state",
        "selection_rule":"first solve palms to actual near grip surfaces with fixed rifle; then solve each digit toward far grip surfaces using collision-bounded candidates",
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
        "human_scale_rifle_world_transform_preserved":True,
        "v0_4_center_socket_contact_superseded_for_physical_grip":True,
        "real_weapon_grip_volumes_used":True,
        "v0_5_visual_result_promoted":False,
        "v0_6_native_result_promoted":False,
        "production_grip_claim":False,
        "automatic_visual_promotion":False,
        "notes":[
            "v0.7 does not move or rescale the rifle. It changes where the existing character palm socket is asked to contact the weapon: near physical surface instead of component center.",
            "The shared shoulder/elbow/wrist chain is re-solved to the surface palm target before any finger rotation is applied.",
            "Finger curl remains source-grounded and collision-bounded against the real primary-grip/foregrip volumes.",
            "v0.5 remains mechanically green but visually rejected; v0.6 remains a useful native rejection showing finger-only repair is impossible from the center-socket palm state.",
            "Only preserved Godot front, three-quarter and hand-close evidence may promote v0.7."
        ],
    }
    if not all(acceptance.values()):
        raise ValueError(f"v0.7 physical grip acceptance failed: {acceptance}; palm={result['surface_palm_contact']}; finger={result['finger_grip']}")
    return posed_mesh,result


def build_preferred_physical_grip_rifle_contact_pose():
    body,_uv,_state=_load_identity_body()
    return build_physical_grip_rifle_contact_pose(body)


if __name__=="__main__":
    import json
    mesh,packet=build_preferred_physical_grip_rifle_contact_pose()
    print(json.dumps({"vertices":len(mesh.vertices),"faces":len(mesh.faces),"acceptance":packet["acceptance"],"surface_palm_contact":packet["surface_palm_contact"],"finger_grip":packet["finger_grip"]},indent=2))
