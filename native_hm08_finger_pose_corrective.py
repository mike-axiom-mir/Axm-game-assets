#!/usr/bin/env python3
"""Bind-volume-driven pose-space finger correctives for the v0.7 rifle grip.

The real Godot grip A/B proved contact but exposed pinched/faceted knuckles and
finger-web compression. DQS improves a radial metric but is visually negligible
with the existing mostly-rigid segment weights. v0.9 therefore keeps the proven
v0.7 LBS pose/contact and adds only bounded pose-space volume restoration around
source-grounded finger pivots.

For each of the 30 finger joints, Forge measures the local radial envelope around
the bind joint axis and the same vertex neighborhood after the v0.7 LBS pose.
Only a measured radial deficit can create a corrective scale. Displacements are
radial to the posed joint axis, smoothly fall off through the source neighborhood,
and are globally capped to 2.5 mm per vertex. Non-finger vertices remain exact.
"""
from __future__ import annotations

from math import acos, sqrt

from native_geometry import Mesh, Vec3, bounds
from native_hm08_finger_rig import _segment_distance, build_hm08_finger_skeleton, build_hm08_finger_skin_weights
from native_hm08_rifle_contact_pose import _add, _distance, _dot, _length, _mul, _normalize, _sub
from native_hm08_rifle_grip_dqs import _reconstruct_v07_skeleton, _segment_endpoints
from native_hm08_rifle_grip_surface_pose import build_grip_surface_finger_pose
from native_hm08_rifle_finger_grip import _aabb_sdf, _quat, _world_to_weapon_local
from native_hm08_undersuit import _load_identity_body
from native_skin import Skeleton, SkinWeights, global_joint_matrices, transform_point
from native_weapon_human_scale import sentinel_rifle_human_scale

SCHEMA="axm.game-assets.hm08-finger-pose-corrective.v0.9"
MAX_VERTEX_CORRECTION_M=0.0025


def _clamp(value:float,lo:float,hi:float)->float:
    return max(lo,min(hi,value))


def _smooth01(value:float)->float:
    t=_clamp(value,0.0,1.0);return t*t*(3.0-2.0*t)


def _line_radial(point:Vec3,pivot:Vec3,axis:Vec3)->tuple[float,Vec3]:
    axis=_normalize(axis)
    delta=_sub(point,pivot)
    radial=_sub(delta,_mul(axis,_dot(delta,axis)))
    return _length(radial),radial


def _joint_frame(skeleton:Skeleton,finger_indices:dict[str,int],tip_offsets:dict[str,object],side:str,digit:int,segment:int):
    matrices=global_joint_matrices(skeleton)
    current=finger_indices[f"{side}_finger{digit}_{segment}"]
    pivot=transform_point(matrices[current],(0.0,0.0,0.0))
    if segment==1:
        parent=skeleton.joints[current].parent
        assert parent is not None
        parent_point=transform_point(matrices[parent],(0.0,0.0,0.0))
    else:
        previous=finger_indices[f"{side}_finger{digit}_{segment-1}"]
        parent_point=transform_point(matrices[previous],(0.0,0.0,0.0))
    if segment<3:
        child=finger_indices[f"{side}_finger{digit}_{segment+1}"]
        child_point=transform_point(matrices[child],(0.0,0.0,0.0))
    else:
        local=tuple(float(v) for v in tip_offsets[f"{side}_finger{digit}_tip"])
        child_point=transform_point(matrices[current],local)
    incoming=_sub(pivot,parent_point);outgoing=_sub(child_point,pivot)
    in_len=_length(incoming);out_len=_length(outgoing)
    in_dir=_normalize(incoming);out_dir=_normalize(outgoing)
    tangent=_add(in_dir,out_dir)
    if _length(tangent)<=1e-8:tangent=out_dir
    tangent=_normalize(tangent)
    cosine=_clamp(_dot(in_dir,out_dir),-1.0,1.0)
    bend_angle=acos(cosine)
    return {"pivot":pivot,"tangent":tangent,"incoming_length_m":in_len,"outgoing_length_m":out_len,"bend_angle_rad":bend_angle}


def _dominant_digit_by_vertex(weights:SkinWeights,finger_indices:dict[str,int])->dict[int,tuple[str,int]]:
    joint_meta={finger_indices[f"{side}_finger{digit}_{segment}"]:(side,digit) for side in ("left","right") for digit in range(1,6) for segment in range(1,4)}
    result={}
    for index,(joint_row,weight_row) in enumerate(zip(weights.joints,weights.weights)):
        active=[(float(weight),joint_meta[joint]) for joint,weight in zip(joint_row,weight_row) if joint in joint_meta and weight>1e-9]
        if active:result[index]=max(active,key=lambda row:(row[0],row[1]))[1]
    return result


def _finger_aabb_penetration(mesh:Mesh,weights:SkinWeights,finger_indices:dict[str,int],weapon_packet:dict[str,object]):
    rifle=sentinel_rifle_human_scale();translation=tuple(float(v) for v in weapon_packet["translation"]);rotation=_quat(weapon_packet["rotation"])
    joint_side={finger_indices[f"{side}_finger{digit}_{segment}"]:side for side in ("left","right") for digit in range(1,6) for segment in range(1,4)}
    component={"right":"primary_grip","left":"foregrip"};values=[]
    for index,(joint_row,weight_row) in enumerate(zip(weights.joints,weights.weights)):
        active=[(float(weight),joint_side[joint]) for joint,weight in zip(joint_row,weight_row) if joint in joint_side and weight>1e-9]
        if not active:continue
        side=max(active,key=lambda row:row[0])[1];lo,hi=bounds(rifle.components[component[side]])
        local=_world_to_weapon_local(mesh.vertices[index],translation,rotation);values.append(max(0.0,-_aabb_sdf(local,lo,hi)))
    return max(values,default=0.0)


def build_finger_pose_corrective(body:Mesh)->tuple[Mesh,dict[str,object]]:
    lbs_mesh,v07=build_grip_surface_finger_pose(body)
    bind,posed,weights,finger_indices,rig_evidence,skin_evidence=_reconstruct_v07_skeleton(body,v07)
    dominant=_dominant_digit_by_vertex(weights,finger_indices)
    tip_offsets=rig_evidence["tip_local_offsets"]
    bind_frames={};pose_frames={};neighborhoods={};joint_receipts={}

    for side in ("left","right"):
        for digit in range(1,6):
            for segment in range(1,4):
                key=f"{side}:{digit}:{segment}"
                bf=_joint_frame(bind,finger_indices,tip_offsets,side,digit,segment)
                pf=_joint_frame(posed,finger_indices,tip_offsets,side,digit,segment)
                bind_frames[key]=bf;pose_frames[key]=pf
                local_length=min(float(bf["incoming_length_m"]),float(bf["outgoing_length_m"]))
                radius=_clamp(local_length*0.62,0.009,0.017)
                rows=[]
                for index,owner in dominant.items():
                    if owner!=(side,digit):continue
                    distance=_distance(body.vertices[index],bf["pivot"])
                    if distance<=radius:rows.append(index)
                neighborhoods[key]={"radius_m":radius,"vertices":rows}

    displacements=[[0.0,0.0,0.0] for _ in body.vertices]
    lbs_joint_errors=[];predicted_joint_errors=[];eligible=0
    for key,neighborhood in neighborhoods.items():
        rows=neighborhood["vertices"]
        if len(rows)<4:
            joint_receipts[key]={"status":"skipped","reason":"too_few_vertices","vertex_count":len(rows)};continue
        bf=bind_frames[key];pf=pose_frames[key];radius=float(neighborhood["radius_m"])
        bind_rad=[_line_radial(body.vertices[i],bf["pivot"],bf["tangent"])[0] for i in rows]
        lbs_rad=[_line_radial(lbs_mesh.vertices[i],pf["pivot"],pf["tangent"])[0] for i in rows]
        bind_mean=sum(bind_rad)/len(bind_rad);lbs_mean=sum(lbs_rad)/len(lbs_rad)
        deficit=max(0.0,bind_mean-lbs_mean)
        # Never inflate more than 22% from this one joint. The measured deficit
        # sets the target; this is not a free aesthetic bulge control.
        scale=1.0 if lbs_mean<=1e-12 else min(1.22,max(1.0,bind_mean/lbs_mean))
        bend_factor=_smooth01(float(pf["bend_angle_rad"])/(1.25))
        effective_scale=1.0+(scale-1.0)*bend_factor
        eligible+=1 if effective_scale>1.000001 else 0
        predicted=[]
        for index,bind_radius in zip(rows,bind_rad):
            posed_radius,radial=_line_radial(lbs_mesh.vertices[index],pf["pivot"],pf["tangent"])
            if posed_radius<=1e-10:continue
            bind_distance=_distance(body.vertices[index],bf["pivot"])
            falloff=_smooth01(1.0-bind_distance/radius)
            amount=(effective_scale-1.0)*falloff
            correction=_mul(radial,amount)
            for axis in range(3):displacements[index][axis]+=correction[axis]
            predicted.append(posed_radius*(1.0+amount))
        lbs_error=abs(lbs_mean-bind_mean)
        predicted_mean=sum(predicted)/len(predicted) if predicted else lbs_mean
        predicted_error=abs(predicted_mean-bind_mean)
        lbs_joint_errors.append(lbs_error);predicted_joint_errors.append(predicted_error)
        joint_receipts[key]={
            "status":"active" if effective_scale>1.000001 else "no_deficit",
            "vertex_count":len(rows),"radius_m":radius,"bind_radial_mean_m":bind_mean,"lbs_radial_mean_m":lbs_mean,
            "measured_deficit_m":deficit,"raw_restore_scale":scale,"bend_angle_rad":pf["bend_angle_rad"],"bend_factor":bend_factor,
            "effective_restore_scale":effective_scale,"lbs_mean_abs_radial_error_m":lbs_error,"predicted_mean_abs_radial_error_m":predicted_error,
        }

    corrected=list(lbs_mesh.vertices);moved=0;max_delta=0.0
    for index,delta in enumerate(displacements):
        length=sqrt(sum(value*value for value in delta))
        if length<=1e-12:continue
        if length>MAX_VERTEX_CORRECTION_M:
            factor=MAX_VERTEX_CORRECTION_M/length;delta=[value*factor for value in delta];length=MAX_VERTEX_CORRECTION_M
        corrected[index]=_add(lbs_mesh.vertices[index],(delta[0],delta[1],delta[2]));moved+=1;max_delta=max(max_delta,length)
    mesh=Mesh("sentinel_hm08_finger_pose_corrective_v0_9",corrected,list(body.faces))

    actual_joint_errors=[];improved_joints=0
    for key,receipt in joint_receipts.items():
        if receipt.get("status") not in ("active","no_deficit"):continue
        rows=neighborhoods[key]["vertices"];bf=bind_frames[key];pf=pose_frames[key]
        bind_mean=float(receipt["bind_radial_mean_m"])
        corrected_rad=[_line_radial(mesh.vertices[i],pf["pivot"],pf["tangent"])[0] for i in rows]
        corrected_mean=sum(corrected_rad)/len(corrected_rad);error=abs(corrected_mean-bind_mean)
        receipt["corrected_radial_mean_m"]=corrected_mean;receipt["corrected_mean_abs_radial_error_m"]=error
        actual_joint_errors.append(error)
        if error+1e-12<float(receipt["lbs_mean_abs_radial_error_m"]):improved_joints+=1

    finger_vertices=set(dominant)
    nonfinger=max((_distance(a,b) for i,(a,b) in enumerate(zip(lbs_mesh.vertices,mesh.vertices)) if i not in finger_vertices),default=0.0)
    lbs_error_mean=sum(lbs_joint_errors)/len(lbs_joint_errors);corrected_error_mean=sum(actual_joint_errors)/len(actual_joint_errors)
    lbs_pen=_finger_aabb_penetration(lbs_mesh,weights,finger_indices,v07["weapon"]);corrected_pen=_finger_aabb_penetration(mesh,weights,finger_indices,v07["weapon"])
    evidence={
        "schema":SCHEMA,"source_pose_schema":v07["schema"],"joint_receipts":joint_receipts,
        "finger_vertex_count":len(finger_vertices),"moved_finger_vertices":moved,"max_vertex_correction_m":max_delta,"correction_cap_m":MAX_VERTEX_CORRECTION_M,
        "radial_volume_error":{"joint_samples":len(actual_joint_errors),"eligible_deficit_joints":eligible,"improved_joints":improved_joints,"lbs_mean_abs_error_m":lbs_error_mean,"corrected_mean_abs_error_m":corrected_error_mean,"relative_error":corrected_error_mean/max(lbs_error_mean,1e-12)},
        "grip_aabb_surface_penetration":{"lbs_max_m":lbs_pen,"corrected_max_m":corrected_pen},
        "nonfinger_max_delta_from_v0_7_lbs_m":nonfinger,"contact_summary":v07["contact_summary"],"finger_rig":rig_evidence,"finger_skin":skin_evidence,
        "truth":{
            "same_v0_7_contact_pose":True,"same_v0_7_weights":True,"corrective_driven_by_measured_bind_volume_deficit":True,
            "corrective_applied_only_to_finger_owned_vertices":True,"production_corrective_claim":False,"automatic_visual_promotion":False,
            "notes":[
                "v0.8 DQS is retained as a valid generic deformation kernel but its same-run Godot delta was visually negligible for these mostly-rigid finger weights.",
                "v0.9 restores only measured local radial deficits around source-grounded finger pivots and caps cumulative motion to 2.5 mm per vertex.",
                "Godot close-view evidence remains mandatory because radial-envelope recovery does not guarantee believable knuckle/webbing anatomy."
            ],
        },
    }
    return mesh,evidence


def build_preferred_finger_pose_corrective():
    body,_uv,_state=_load_identity_body();return build_finger_pose_corrective(body)


if __name__=="__main__":
    import json
    mesh,evidence=build_preferred_finger_pose_corrective();print(json.dumps({"vertices":len(mesh.vertices),"faces":len(mesh.faces),**evidence},indent=2))
