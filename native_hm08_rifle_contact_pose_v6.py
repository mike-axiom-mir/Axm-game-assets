#!/usr/bin/env python3
"""Rifle contact v0.6: wrap fingers around real weapon grip volumes.

v0.5 proved that source-grounded finger joints can be curled while preserving
the v0.4 arm/rifle state, but real Godot close-up evidence rejected its visual
result: optimizing every fingertip toward a single socket center collapsed and
twisted the hand.

v0.6 keeps the same 53-joint skin and preserved arm/rifle transform, but derives
an oriented grip volume from the actual primary-grip / foregrip component mesh.
Each digit receives a target on the far *surface* of that volume relative to its
proximal root. Candidate curls that drive the fingertip too deeply into the
weapon are rejected before target distance is considered.
"""
from __future__ import annotations

import copy
from math import sqrt

from native_geometry import Mesh, bounds
from native_hm08_rifle_contact_pose import _add, _distance, _quat_rotate
from native_hm08_rifle_contact_pose_v5 import (
    SCALE_CANDIDATES,
    _reconstruct_v4_on_finger_rig,
    _solve_digit,
    _tip_world,
)
from native_hm08_undersuit import _load_identity_body
from native_skin import Skeleton, global_joint_matrices, skin_vertices, validate_skeleton
from native_weapon_human_scale import sentinel_rifle_human_scale

SCHEMA = "axm.game-assets.hm08-rifle-contact-pose.v0.6"
SURFACE_CLEARANCE_M = 0.003
AXIAL_MARGIN_FRACTION = 0.12
MAX_TIP_PENETRATION_M = 0.006


def _sub(a, b):
    return a[0]-b[0], a[1]-b[1], a[2]-b[2]


def _mul(a, scalar: float):
    return a[0]*scalar, a[1]*scalar, a[2]*scalar


def _dot(a, b) -> float:
    return a[0]*b[0]+a[1]*b[1]+a[2]*b[2]


def _length(a) -> float:
    return sqrt(_dot(a,a))


def _normalize(a):
    length=_length(a)
    if length<=1e-12:
        raise ValueError("cannot normalize zero grip-volume vector")
    return a[0]/length,a[1]/length,a[2]/length


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo,min(hi,value))


def _mean(points):
    if not points:
        raise ValueError("grip volume needs vertices")
    inv=1.0/len(points)
    return tuple(sum(point[axis] for point in points)*inv for axis in range(3))


def _mat_vec(matrix, vector):
    return tuple(sum(matrix[row][col]*vector[col] for col in range(3)) for row in range(3))


def _principal_axis(points):
    center=_mean(points)
    covariance=[[0.0,0.0,0.0] for _ in range(3)]
    for point in points:
        delta=_sub(point,center)
        for row in range(3):
            for col in range(3):
                covariance[row][col]+=delta[row]*delta[col]
    spans=[]
    for axis in range(3):
        values=[point[axis] for point in points]
        spans.append(max(values)-min(values))
    vector=[0.0,0.0,0.0]
    vector[max(range(3),key=lambda axis:spans[axis])]=1.0
    for _ in range(24):
        candidate=_mat_vec(covariance,vector)
        length=sqrt(sum(value*value for value in candidate))
        if length<=1e-12:
            raise ValueError("grip covariance produced no principal axis")
        vector=[value/length for value in candidate]
    axis=tuple(vector)
    projections=[_dot(_sub(point,center),axis) for point in points]
    return center,axis,min(projections),max(projections)


def _world_mesh(mesh: Mesh, rotation, translation, *, name: str) -> Mesh:
    return Mesh(name,[_add(translation,_quat_rotate(rotation,point)) for point in mesh.vertices],list(mesh.faces))


def _grip_volume(component: Mesh, rotation, translation, *, name: str) -> dict[str,object]:
    world=_world_mesh(component,rotation,translation,name=name)
    center,axis,t_min,t_max=_principal_axis(world.vertices)
    span=t_max-t_min
    if span<=0.04:
        raise ValueError(f"grip component {name} has implausibly short principal span {span}")
    radial_rows=[]
    for vertex in world.vertices:
        delta=_sub(vertex,center)
        t=_dot(delta,axis)
        radial_rows.append(_sub(delta,_mul(axis,t)))
    max_radius=max(_length(row) for row in radial_rows)
    min_positive_radius=min((_length(row) for row in radial_rows if _length(row)>1e-9),default=0.0)
    return {
        "name":name,
        "mesh":world,
        "center":center,
        "axis":axis,
        "t_min":t_min,
        "t_max":t_max,
        "span":span,
        "radial_rows":radial_rows,
        "max_radius":max_radius,
        "min_positive_radius":min_positive_radius,
    }


def _surface_target(volume: dict[str,object], root_world, fallback_world) -> tuple[tuple[float,float,float],dict[str,object]]:
    center=volume["center"];axis=volume["axis"]
    assert isinstance(center,tuple) and isinstance(axis,tuple)
    t_raw=_dot(_sub(root_world,center),axis)
    margin=float(volume["span"])*AXIAL_MARGIN_FRACTION
    t=_clamp(t_raw,float(volume["t_min"])+margin,float(volume["t_max"])-margin)
    centerline=_add(center,_mul(axis,t))
    radial=_sub(root_world,centerline)
    radial=_sub(radial,_mul(axis,_dot(radial,axis)))
    if _length(radial)<=1e-8:
        radial=_sub(fallback_world,centerline)
        radial=_sub(radial,_mul(axis,_dot(radial,axis)))
    toward_root=_normalize(radial)
    target_direction=_mul(toward_root,-1.0)
    support=max(_dot(row,target_direction) for row in volume["radial_rows"])
    if support<=0.0:
        raise ValueError(f"grip volume {volume['name']} has no positive far-side support")
    target=_add(centerline,_mul(target_direction,support+SURFACE_CLEARANCE_M))
    return target,{
        "root_axial_projection_m":t_raw,
        "target_axial_projection_m":t,
        "axial_clamped":abs(t-t_raw)>1e-12,
        "target_direction_from_axis":list(target_direction),
        "support_radius_m":support,
        "surface_clearance_m":SURFACE_CLEARANCE_M,
        "target_world":list(target),
    }


def _surface_gap(volume: dict[str,object], point) -> dict[str,float]:
    center=volume["center"];axis=volume["axis"]
    assert isinstance(center,tuple) and isinstance(axis,tuple)
    delta=_sub(point,center)
    t=_dot(delta,axis)
    centerline=_add(center,_mul(axis,t))
    radial=_sub(point,centerline)
    radial=_sub(radial,_mul(axis,_dot(radial,axis)))
    distance=_length(radial)
    if distance<=1e-9:
        return {"axial_m":t,"radial_m":0.0,"support_radius_m":float(volume["max_radius"]),"surface_gap_m":-float(volume["max_radius"])}
    direction=_mul(radial,1.0/distance)
    support=max(_dot(row,direction) for row in volume["radial_rows"])
    return {"axial_m":t,"radial_m":distance,"support_radius_m":support,"surface_gap_m":distance-support}


def build_grip_volume_rifle_contact_pose(body_m: Mesh) -> tuple[Mesh,dict[str,object]]:
    (
        _v4_mesh,v4,bind,weights,indices,rig_evidence,skin_evidence,open_skeleton,open_mesh,arm_rotation_exact
    )=_reconstruct_v4_on_finger_rig(body_m)
    weapon=sentinel_rifle_human_scale()
    rotation=tuple(float(value) for value in v4["weapon"]["rotation"])
    translation=tuple(float(value) for value in v4["weapon"]["translation"])
    volumes={
        "right":_grip_volume(weapon.components["primary_grip"],rotation,translation,name="primary_grip"),
        "left":_grip_volume(weapon.components["foregrip"],rotation,translation,name="foregrip"),
    }

    open_globals=global_joint_matrices(open_skeleton)
    current=open_skeleton
    choices={}
    all_improvements=[]
    final_surface_gaps=[]
    for side in ("right","left"):
        side_rows={"volume":{},"digits":{}}
        volume=volumes[side]
        side_rows["volume"]={
            "name":volume["name"],
            "center_world":list(volume["center"]),
            "principal_axis_world":list(volume["axis"]),
            "axial_range_m":[volume["t_min"],volume["t_max"]],
            "axial_span_m":volume["span"],
            "max_radial_extent_m":volume["max_radius"],
        }
        for digit in range(1,6):
            root_index=indices[f"{side}_finger{digit}_1"]
            root_world=(open_globals[root_index][0][3],open_globals[root_index][1][3],open_globals[root_index][2][3])
            open_tip=_tip_world(current,indices,rig_evidence,side,digit)
            target,target_meta=_surface_target(volume,root_world,open_tip)
            open_target_error=_distance(open_tip,target)
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
            safe_candidate_count=sum(1 for row in candidates if row[0]==0)
            if safe_candidate_count<=0:
                raise ValueError(f"no collision-safe curl candidate for {side} digit {digit}: {[(row[1],row[2],row[3]) for row in candidates]}")
            _unsafe,target_error,penetration,scale,current,tip,segments,gap=candidates[0]
            improvement=open_target_error-target_error
            final_surface_gaps.append(float(gap["surface_gap_m"]))
            all_improvements.append(improvement)
            side_rows["digits"][str(digit)]={
                "root_world":list(root_world),
                "open_tip_world":list(open_tip),
                "target":target_meta,
                "scale":scale,
                "safe_candidate_count":safe_candidate_count,
                "maximum_allowed_tip_penetration_m":MAX_TIP_PENETRATION_M,
                "selected_tip_penetration_m":penetration,
                "open_tip_to_surface_target_m":open_target_error,
                "curled_tip_to_surface_target_m":target_error,
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
        raise ValueError(f"v0.6 posed skeleton invalid: {posed_report}")
    posed_mesh=Mesh("sentinel_hm08_grip_volume_rifle_contact_v0_6",skin_vertices(body_m,weights,bind,posed),list(body_m.faces))

    finger_joint_set=set(rig_evidence["finger_indices"].values())
    curl_moved=0;finger_curl_max=0.0;nonfinger_curl_max=0.0
    for index,(before,after) in enumerate(zip(open_mesh.vertices,posed_mesh.vertices)):
        delta=_distance(before,after)
        active=any(joint in finger_joint_set and weight>1e-9 for joint,weight in zip(weights.joints[index],weights.weights[index]))
        if active:
            if delta>1e-10:curl_moved+=1
            finger_curl_max=max(finger_curl_max,delta)
        else:
            nonfinger_curl_max=max(nonfinger_curl_max,delta)

    lo,hi=bounds(body_m);height=hi[1]-lo[1]
    head_indices=[index for index,point in enumerate(body_m.vertices) if point[1]>=lo[1]+height*0.84]
    lower_indices=[index for index,point in enumerate(body_m.vertices) if point[1]<=lo[1]+height*0.50]
    head_curl=max(_distance(open_mesh.vertices[index],posed_mesh.vertices[index]) for index in head_indices)
    lower_curl=max(_distance(open_mesh.vertices[index],posed_mesh.vertices[index]) for index in lower_indices)
    skin_preserved=(
        skin_evidence["preserved_nonfinger_rows"]==skin_evidence["expected_preserved_nonfinger_rows"]
        and skin_evidence["truth"]["shared_body_skin_preserved_outside_fingers"] is True
    )
    minimum_improvement=min(all_improvements)
    max_deep_penetration=max(0.0,-min(final_surface_gaps))

    acceptance={
        "finger_rig_53_joints":len(bind.joints)==53 and rig_evidence["finger_joint_count"]==30,
        "finger_skin_green":skin_evidence["validation"]["status"]=="pass" and skin_evidence["minimum_vertices_per_segment"]>=3,
        "finger_skin_preserves_nonfinger_v2_rows":skin_preserved,
        "v0_4_arm_joint_rotations_preserved":arm_rotation_exact,
        "human_scale_rifle_preserved":v4["weapon"]["scale"]==[1.0,1.0,1.0],
        "primary_contact_preserved":float(v4["contact"]["primary_position_error"])<1e-8,
        "support_contact_preserved":float(v4["contact"]["support_position_error"])<1e-6,
        "real_grip_components_used":volumes["right"]["name"]=="primary_grip" and volumes["left"]["name"]=="foregrip",
        "all_surface_targets_outside_grip":all(abs(float(row["target"]["surface_clearance_m"])-SURFACE_CLEARANCE_M)<1e-12 for side in ("right","left") for row in choices[side]["digits"].values()),
        "every_digit_has_collision_safe_candidate":all(int(row["safe_candidate_count"])>0 for side in ("right","left") for row in choices[side]["digits"].values()),
        "every_fingertip_closer_to_surface_target":len(all_improvements)==10 and minimum_improvement>1e-6,
        "both_hand_target_means_closer":all(choices[side]["curled_target_mean_m"]<choices[side]["open_target_mean_m"] for side in ("right","left")),
        "finger_surface_moves":curl_moved>200 and finger_curl_max>0.003,
        "nonfinger_rows_stationary_under_curl":nonfinger_curl_max<1e-8,
        "head_unchanged_by_curl":head_curl<1e-9,
        "lower_body_unchanged_by_curl":lower_curl<1e-9,
        "curl_bounded":finger_curl_max<0.12,
        "tip_penetration_bounded":max_deep_penetration<=MAX_TIP_PENETRATION_M+1e-12,
        "posed_skeleton_valid":posed_report["status"]=="pass",
    }

    result=copy.deepcopy(v4)
    result["schema"]=SCHEMA
    result["pose_id"]="cross_chest_low_ready_grip_volume_v0.6"
    result["shared_rig"]={
        "schema":rig_evidence["schema"],
        "joint_count":len(bind.joints),
        "finger_joint_count":rig_evidence["finger_joint_count"],
        "finger_indices":rig_evidence["finger_indices"],
        "finger_rig_evidence":rig_evidence,
        "finger_skin_evidence":skin_evidence,
    }
    result["finger_grip"]={
        "changed_variable_from_v0_5":"target_geometry_and_candidate_selection_socket_center_to_collision_aware_real_component_surface_volume",
        "v0_5_visual_status":"rejected_real_godot_hand_close_crushed_twisted_fingers",
        "selection_rule":"derive far-surface targets from real primary_grip/foregrip geometry; reject candidate curls deeper than the fingertip penetration budget before minimizing target error",
        "surface_clearance_m":SURFACE_CLEARANCE_M,
        "maximum_tip_penetration_m":MAX_TIP_PENETRATION_M,
        "axial_margin_fraction":AXIAL_MARGIN_FRACTION,
        "scale_candidates":list(SCALE_CANDIDATES),
        "choices":choices,
        "minimum_target_improvement_m":minimum_improvement,
        "mean_target_improvement_m":sum(all_improvements)/len(all_improvements),
        "final_tip_surface_gap_m_range":[min(final_surface_gaps),max(final_surface_gaps)],
        "max_deep_tip_penetration_m":max_deep_penetration,
        "curl_moved_finger_vertices":curl_moved,
        "finger_curl_max_displacement_m":finger_curl_max,
        "nonfinger_curl_max_displacement_m":nonfinger_curl_max,
        "head_curl_max_displacement_m":head_curl,
        "lower_body_curl_max_displacement_m":lower_curl,
    }
    result["acceptance"]=acceptance
    result["truth"]={
        "uses_shared_full_body_rig":True,
        "source_grounded_finger_chains":True,
        "v0_4_arm_pose_preserved":True,
        "human_scale_rifle_preserved":True,
        "real_weapon_grip_volume_used":True,
        "v0_5_visual_result_promoted":False,
        "production_grip_claim":False,
        "automatic_visual_promotion":False,
        "notes":[
            "v0.5 is preserved as a mechanically green but visually rejected attempt because socket-center targeting crushed/twisted fingers in real Godot evidence.",
            "v0.6 derives an oriented volume from the actual primary-grip and foregrip meshes after the proven rifle world transform.",
            "Each finger root chooses an axial slice; the fingertip target sits on the far support surface of that slice plus 3 mm clearance, encouraging a wrap rather than convergence inside the weapon.",
            "The first v0.6 pass showed that target-distance minimization alone could still choose a shortcut through the grip. Candidate selection now rejects fingertip penetration deeper than 6 mm before comparing target error.",
            "Surface-target and penetration metrics are proposal evidence only. The exact preserved Godot hand-close camera decides whether v0.6 is visually usable.",
            "Metacarpal articulation and compressed-knuckle correctives remain later quality gates even if v0.6 improves the gross wrap."
        ],
    }
    if not all(acceptance.values()):
        raise ValueError(f"v0.6 grip-volume acceptance failed: {acceptance}; minimum_improvement={minimum_improvement:.9g}; surface_gaps={result['finger_grip']['final_tip_surface_gap_m_range']}; choices={choices}")
    return posed_mesh,result


def build_preferred_grip_volume_rifle_contact_pose():
    body,_uv,_state=_load_identity_body()
    return build_grip_volume_rifle_contact_pose(body)


if __name__=="__main__":
    import json
    mesh,packet=build_preferred_grip_volume_rifle_contact_pose()
    print(json.dumps({"vertices":len(mesh.vertices),"faces":len(mesh.faces),"acceptance":packet["acceptance"],"finger_grip":packet["finger_grip"]},indent=2))
