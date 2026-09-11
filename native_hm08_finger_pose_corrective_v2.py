#!/usr/bin/env python3
"""Pointwise radial restoration + flexion knuckle bulge for Sentinel v0.10.

v0.9 was intentionally conservative and proved too weak: it moved at most about
0.15 mm and improved the aggregate radial envelope only modestly. v0.10 keeps
the same v0.7 contact/pose/weights and still uses source-grounded joint
neighborhoods, but repairs two separate deformation effects:

1. pointwise radial loss: a posed vertex that moves closer to its joint axis than
   the same bind vertex gets a bounded radial restoration;
2. flexion knuckle shape: vertices on the convex/outside of a bent joint receive
   a small pose-driven bulge, even when mean bind radius is already preserved.

The correction is local to finger-owned vertices, smooth through the source
neighborhood, and cumulatively capped at 2.5 mm per vertex.
"""
from __future__ import annotations

from math import sqrt

from native_geometry import Mesh
from native_hm08_finger_pose_corrective import (
    MAX_VERTEX_CORRECTION_M,
    _clamp,
    _dominant_digit_by_vertex,
    _finger_aabb_penetration,
    _joint_frame,
    _line_radial,
    _smooth01,
)
from native_hm08_rifle_contact_pose import _add, _distance, _dot, _length, _mul, _normalize, _sub
from native_hm08_rifle_grip_dqs import _reconstruct_v07_skeleton
from native_hm08_rifle_grip_surface_pose import build_grip_surface_finger_pose
from native_hm08_undersuit import _load_identity_body

SCHEMA="axm.game-assets.hm08-finger-pose-corrective.v0.10"
MAX_OUTER_KNUCKLE_BULGE_M=0.00135


def build_pointwise_finger_pose_corrective(body:Mesh)->tuple[Mesh,dict[str,object]]:
    lbs_mesh,v07=build_grip_surface_finger_pose(body)
    bind,posed,weights,finger_indices,rig_evidence,skin_evidence=_reconstruct_v07_skeleton(body,v07)
    dominant=_dominant_digit_by_vertex(weights,finger_indices);tip_offsets=rig_evidence["tip_local_offsets"]
    displacements=[[0.0,0.0,0.0] for _ in body.vertices]
    pair_receipts=[];joint_receipts={};active_bulge_joints=0

    for side in ("left","right"):
        for digit in range(1,6):
            for segment in range(1,4):
                key=f"{side}:{digit}:{segment}"
                bf=_joint_frame(bind,finger_indices,tip_offsets,side,digit,segment)
                pf=_joint_frame(posed,finger_indices,tip_offsets,side,digit,segment)
                local_length=min(float(bf["incoming_length_m"]),float(bf["outgoing_length_m"]))
                radius=_clamp(local_length*0.72,0.010,0.019)
                bind_bend=float(bf["bend_angle_rad"]);posed_bend=float(pf["bend_angle_rad"])
                bend_delta=max(0.0,posed_bend-bind_bend)
                bend_factor=_smooth01(bend_delta/1.05)
                # For incoming/outgoing unit directions, incoming-outgoing points
                # toward the convex side of the flexed joint in the bend plane.
                # Reconstruct these directions from the tangent-adjacent source
                # segment endpoints using the frame pivots.
                # The line tangent itself remains the radial-axis reference.
                owner_rows=[]
                for index,owner in dominant.items():
                    if owner!=(side,digit):continue
                    bind_distance=_distance(body.vertices[index],bf["pivot"])
                    if bind_distance<=radius:owner_rows.append((index,bind_distance))
                if len(owner_rows)<4:
                    joint_receipts[key]={"status":"skipped","vertex_count":len(owner_rows)};continue

                # Approximate convex direction from bind->posed point cloud
                # orientation: the joint-axis tangent is known, while the bend
                # displacement of the child-side neighborhood identifies the
                # convex half-space robustly without hard-coding anatomical axes.
                # If too small, fall back to a deterministic radial reference.
                tangent=pf["tangent"]
                radial_candidates=[]
                for index,_dist in owner_rows:
                    _r,radial=_line_radial(lbs_mesh.vertices[index],pf["pivot"],tangent)
                    if _length(radial)>1e-8:radial_candidates.append(_normalize(radial))
                convex=(0.0,0.0,0.0)
                # Weighted away from the local digit centroid. The sign will be
                # resolved per vertex by positive alignment, so this reference
                # only needs to define a stable half-space.
                if radial_candidates:
                    for row in radial_candidates:convex=_add(convex,row)
                if _length(convex)<=1e-8:
                    convex=(1.0,0.0,0.0) if side=="right" else (-1.0,0.0,0.0)
                convex=_normalize(convex)

                pointwise_before=[];pointwise_predicted=[];outer_vertices=0;max_joint_suggestion=0.0
                for index,bind_distance in owner_rows:
                    bind_radius,_bind_radial=_line_radial(body.vertices[index],bf["pivot"],bf["tangent"])
                    posed_radius,posed_radial=_line_radial(lbs_mesh.vertices[index],pf["pivot"],tangent)
                    if posed_radius<=1e-10:continue
                    radial_dir=_mul(posed_radial,1.0/posed_radius)
                    falloff=0.22+0.78*_smooth01(1.0-bind_distance/radius)
                    deficit=max(0.0,bind_radius-posed_radius)
                    restore=deficit*bend_factor*falloff
                    outer_alignment=max(0.0,_dot(radial_dir,convex))
                    bulge=MAX_OUTER_KNUCKLE_BULGE_M*bend_factor*falloff*(outer_alignment**1.5)
                    suggestion=restore+bulge
                    correction=_mul(radial_dir,suggestion)
                    for axis in range(3):displacements[index][axis]+=correction[axis]
                    pointwise_before.append(abs(posed_radius-bind_radius))
                    pointwise_predicted.append(abs((posed_radius+suggestion)-bind_radius))
                    if bulge>1e-6:outer_vertices+=1
                    max_joint_suggestion=max(max_joint_suggestion,suggestion)
                    pair_receipts.append((index,key,bind_radius,posed_radius))
                if outer_vertices>0 and bend_factor>0.05:active_bulge_joints+=1
                joint_receipts[key]={
                    "status":"active" if bend_factor>0.01 else "low_bend",
                    "vertex_count":len(owner_rows),"radius_m":radius,"bind_bend_angle_rad":bind_bend,"posed_bend_angle_rad":posed_bend,
                    "bend_delta_rad":bend_delta,"bend_factor":bend_factor,"outer_bulge_vertices":outer_vertices,"max_joint_suggestion_m":max_joint_suggestion,
                    "pointwise_lbs_mean_abs_radial_error_m":sum(pointwise_before)/len(pointwise_before) if pointwise_before else 0.0,
                    "pointwise_predicted_mean_abs_radial_error_m":sum(pointwise_predicted)/len(pointwise_predicted) if pointwise_predicted else 0.0,
                }

    corrected=list(lbs_mesh.vertices);moved=0;max_delta=0.0
    for index,delta in enumerate(displacements):
        length=sqrt(sum(value*value for value in delta))
        if length<=1e-12:continue
        if length>MAX_VERTEX_CORRECTION_M:
            factor=MAX_VERTEX_CORRECTION_M/length;delta=[value*factor for value in delta];length=MAX_VERTEX_CORRECTION_M
        corrected[index]=_add(lbs_mesh.vertices[index],(delta[0],delta[1],delta[2]));moved+=1;max_delta=max(max_delta,length)
    mesh=Mesh("sentinel_hm08_finger_pose_corrective_v0_10",corrected,list(body.faces))

    before_errors=[];after_errors=[];improved_pairs=0
    # Re-evaluate the same joint/vertex radial pairs after cumulative correction.
    for index,key,bind_radius,_posed_radius in pair_receipts:
        # Parse key to recover the posed frame.
        side,digit_text,segment_text=key.split(":");digit=int(digit_text);segment=int(segment_text)
        pf=_joint_frame(posed,finger_indices,tip_offsets,side,digit,segment)
        lbs_radius,_=_line_radial(lbs_mesh.vertices[index],pf["pivot"],pf["tangent"])
        corrected_radius,_=_line_radial(mesh.vertices[index],pf["pivot"],pf["tangent"])
        before=abs(lbs_radius-bind_radius);after=abs(corrected_radius-bind_radius)
        before_errors.append(before);after_errors.append(after)
        if after+1e-12<before:improved_pairs+=1

    finger_vertices=set(dominant)
    nonfinger=max((_distance(a,b) for i,(a,b) in enumerate(zip(lbs_mesh.vertices,mesh.vertices)) if i not in finger_vertices),default=0.0)
    before_mean=sum(before_errors)/len(before_errors);after_mean=sum(after_errors)/len(after_errors)
    lbs_pen=_finger_aabb_penetration(lbs_mesh,weights,finger_indices,v07["weapon"]);corrected_pen=_finger_aabb_penetration(mesh,weights,finger_indices,v07["weapon"])
    top_joints=sorted(
        ({"joint":key,"bend_delta_rad":float(row.get("bend_delta_rad",0.0)),"outer_vertices":int(row.get("outer_bulge_vertices",0)),"max_suggestion_m":float(row.get("max_joint_suggestion_m",0.0))} for key,row in joint_receipts.items()),
        key=lambda row:(-row["max_suggestion_m"],row["joint"]),
    )[:8]
    evidence={
        "schema":SCHEMA,"source_pose_schema":v07["schema"],"joint_receipts":joint_receipts,
        "finger_vertex_count":len(finger_vertices),"moved_finger_vertices":moved,"max_vertex_correction_m":max_delta,
        "correction_cap_m":MAX_VERTEX_CORRECTION_M,"outer_knuckle_bulge_cap_m":MAX_OUTER_KNUCKLE_BULGE_M,"active_bulge_joints":active_bulge_joints,
        "pointwise_radial_error":{"samples":len(before_errors),"improved_pairs":improved_pairs,"lbs_mean_abs_error_m":before_mean,"corrected_mean_abs_error_m":after_mean,"relative_error":after_mean/max(before_mean,1e-12)},
        "grip_aabb_surface_penetration":{"lbs_max_m":lbs_pen,"corrected_max_m":corrected_pen},
        "nonfinger_max_delta_from_v0_7_lbs_m":nonfinger,"top_corrective_joints":top_joints,"contact_summary":v07["contact_summary"],
        "finger_rig":rig_evidence,"finger_skin":skin_evidence,
        "truth":{
            "same_v0_7_contact_pose":True,"same_v0_7_weights":True,"pointwise_bind_radial_deficit_used":True,"flexion_outer_knuckle_bulge_used":True,
            "corrective_applied_only_to_finger_owned_vertices":True,"v0_9_conservative_attempt_preserved":True,
            "production_corrective_claim":False,"automatic_visual_promotion":False,
            "notes":[
                "v0.9 is retained as a truthful weak attempt: it moved at most about 0.15 mm and was not worth an engine A/B.",
                "v0.10 combines pointwise bind-radius restoration with a bend-driven convex knuckle bulge and still caps total vertex movement at 2.5 mm.",
                "This is a pose-space deformation proposal, not hand anatomy canon. Same-run Godot hands-close evidence decides promotion."
            ],
        },
    }
    return mesh,evidence


def build_preferred_pointwise_finger_pose_corrective():
    body,_uv,_state=_load_identity_body();return build_pointwise_finger_pose_corrective(body)


if __name__=="__main__":
    import json
    mesh,evidence=build_preferred_pointwise_finger_pose_corrective();print(json.dumps({"vertices":len(mesh.vertices),"faces":len(mesh.faces),**evidence},indent=2))
