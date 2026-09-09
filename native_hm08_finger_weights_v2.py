#!/usr/bin/env python3
"""Palm/web-aware source-grounded finger skin weights v0.2.

The original finger weights classified each lateral vertex by one nearest bone
segment and completed the hand->proximal-finger transition inside the first 22%
of the source segment. Real deep-grip evidence exposed hard root seams and
triangular webbing under flexion.

v0.2 preserves the same 53-joint skeleton and pinned source bone segments but
changes only the surface ownership/blend rule:
- a tighter finger-neighborhood radius reduces accidental palm capture;
- the source-grounded thumb proximal segment gets a small dedicated radius
  expansion because it leaves the palm obliquely rather than in the long-finger
  fan;
- the hand->first-phalanx transition spans 40% of the proximal segment;
- ambiguous space between two proximal long digits is an explicit web
  transition, shared by the hand joint and both adjacent finger roots;
- inter-phalange blends widen to 30% at each end of a segment.

Everything outside the classified lateral finger/root neighborhoods retains the
promoted humanoid skin v0.2 rows exactly.
"""
from __future__ import annotations

from pathlib import Path

from native_geometry import Mesh, Vec3, bounds
from native_hm08_finger_rig import (
    FINGER_SEED,
    _distance,
    _finger_rows,
    _row,
    _segment_distance,
    _smooth01,
    _source_side_mapping,
    load_finger_landmarks,
)
from native_hm08_humanoid_rig import build_hm08_humanoid_skeleton, derive_hm08_rig_landmarks
from native_hm08_humanoid_skin_v2 import build_hm08_skin_weights_v2
from native_skin import Skeleton,SkinWeights,skin_vertices,validate_skin_weights

SCHEMA="axm.game-assets.hm08-finger-skin.v0.2"
THUMB_PROXIMAL_RADIUS_MULTIPLIER=1.22
THUMB_PROXIMAL_RADIUS_CAP_M=0.0215


def build_hm08_finger_skin_weights_v2(
    body:Mesh,
    skeleton:Skeleton,
    finger_indices:dict[str,int],
    *,
    landmark_path:str|Path=FINGER_SEED,
)->tuple[SkinWeights,dict[str,object]]:
    packet=load_finger_landmarks(landmark_path);mapping=_source_side_mapping(packet);rows=_finger_rows(packet,mapping)
    landmarks=derive_hm08_rig_landmarks(body)
    base_skeleton,_base_rig_evidence,base_indices=build_hm08_humanoid_skeleton(body)
    base_weights,base_skin_evidence=build_hm08_skin_weights_v2(body,base_skeleton,landmarks,base_indices)
    joints=[tuple(row) for row in base_weights.joints];weights=[tuple(row) for row in base_weights.weights]

    lo,hi=bounds(body);half_width=max(abs(lo[0]),abs(hi[0]),1e-9)
    segment_rows={};segment_radii={}
    for side in ("left","right"):
        for digit in range(1,6):
            for segment in range(1,4):
                row=rows[(side,digit,segment)]
                head=tuple(float(value) for value in row["head_m"]);tail=tuple(float(value) for value in row["tail_m"])
                length=_distance(head,tail);radius=max(0.0080,min(0.0175,length*0.40+0.0032))
                if digit==1 and segment==1:
                    radius=min(THUMB_PROXIMAL_RADIUS_CAP_M,radius*THUMB_PROXIMAL_RADIUS_MULTIPLIER)
                current=finger_indices[f"{side}_finger{digit}_{segment}"]
                parent=base_indices[f"{side}_hand"] if segment==1 else finger_indices[f"{side}_finger{digit}_{segment-1}"]
                child=finger_indices[f"{side}_finger{digit}_{segment+1}"] if segment<3 else None
                key=f"{side}:{digit}:{segment}";segment_rows[key]=(head,tail,radius,current,parent,child);segment_radii[key]=radius

    overridden=set();webbing=set();proximal_transition=set();inter_joint_transition=set()
    assigned_by_segment={key:0 for key in segment_rows};assigned_by_side={"left":0,"right":0}
    normalized_distance_max=0.0
    webbing_pairs={}
    for vertex_index,point in enumerate(body.vertices):
        if abs(point[0])<half_width*0.77:continue
        side="left" if point[0]<0.0 else "right"
        candidates=[];root_candidates=[]
        for digit in range(1,6):
            for segment in range(1,4):
                key=f"{side}:{digit}:{segment}";head,tail,radius,current,parent,child=segment_rows[key]
                distance,t=_segment_distance(point,head,tail);row=(distance/radius,distance,t,key,current,parent,child,digit,segment)
                candidates.append(row)
                if segment==1:root_candidates.append(row)
        normalized,distance,t,key,current,parent,child,digit,segment=min(candidates,key=lambda row:(row[0],row[3]))
        if normalized>1.22:continue

        roots=sorted(root_candidates,key=lambda row:(row[0],row[7]))
        r1,r2=roots[0],roots[1]
        # Long-finger webbing is intentionally shared. Thumb-index webbing has
        # a different saddle geometry, so v0.2 keeps it in the widened
        # hand->thumb transition rather than forcing the same two-root rule.
        ambiguous_root=(
            digit!=1 and int(r1[7])!=1 and int(r2[7])!=1 and
            segment==1 and t<0.46 and
            r1[2]<0.48 and r2[2]<0.48 and
            r2[0]<=1.28 and (r2[0]-r1[0])<=0.30
        )
        if ambiguous_root:
            hand=base_indices[f"{side}_hand"]
            j1=r1[4];j2=r2[4]
            # Hand remains the main owner of true webbing; the two adjacent
            # proximal bones share the remaining deformation according to
            # source-segment proximity.
            s1=1.0/max(r1[0],0.18);s2=1.0/max(r2[0],0.18);total=s1+s2
            finger_share=0.42
            w1=finger_share*s1/total;w2=finger_share*s2/total
            joint_row,weight_row=_row((hand,1.0-finger_share),(j1,w1),(j2,w2))
            webbing.add(vertex_index);pair=tuple(sorted((int(r1[7]),int(r2[7]))));webbing_pairs[str(pair)]=webbing_pairs.get(str(pair),0)+1
        elif segment==1 and t<0.40:
            blend=_smooth01(t/0.40)
            joint_row,weight_row=_row((parent,1.0-blend),(current,blend));proximal_transition.add(vertex_index)
        elif t<0.30:
            blend=_smooth01(t/0.30)
            joint_row,weight_row=_row((parent,1.0-blend),(current,blend));inter_joint_transition.add(vertex_index)
        elif child is not None and t>0.70:
            blend=_smooth01((t-0.70)/0.30)
            joint_row,weight_row=_row((current,1.0-blend),(child,blend));inter_joint_transition.add(vertex_index)
        else:
            joint_row,weight_row=_row((current,1.0))
        joints[vertex_index]=joint_row;weights[vertex_index]=weight_row;overridden.add(vertex_index)
        assigned_by_segment[key]+=1;assigned_by_side[side]+=1;normalized_distance_max=max(normalized_distance_max,normalized)

    result=SkinWeights(joints,weights);validation=validate_skin_weights(result,vertex_count=len(body.vertices),joint_count=len(skeleton.joints))
    if validation["status"]!="pass":raise ValueError(f"hm08 finger skin v0.2 invalid: {validation}")
    uninfluenced=sorted(key for key,count in assigned_by_segment.items() if count==0)
    if uninfluenced:raise ValueError(f"v0.2 finger segments received no surface vertices: {uninfluenced}")
    preserved=sum(1 for index in range(len(body.vertices)) if index not in overridden and joints[index]==base_weights.joints[index] and weights[index]==base_weights.weights[index])
    bind_vertices=skin_vertices(body,result,skeleton,skeleton);bind_error=max(_distance(a,b) for a,b in zip(body.vertices,bind_vertices))
    active_counts=[sum(1 for value in row if value>1e-8) for row in weights]
    transition=set(webbing)|set(proximal_transition)|set(inter_joint_transition)
    evidence={
        "schema":SCHEMA,"base_skin_schema":base_skin_evidence["schema"],"vertex_count":len(body.vertices),"joint_count":len(skeleton.joints),
        "overridden_finger_root_vertices":len(overridden),"assigned_by_side":assigned_by_side,"assigned_by_segment":assigned_by_segment,
        "minimum_vertices_per_segment":min(assigned_by_segment.values()),"normalized_segment_distance_max":normalized_distance_max,
        "segment_radius_m":segment_radii,
        "thumb_proximal_radius_multiplier":THUMB_PROXIMAL_RADIUS_MULTIPLIER,
        "thumb_proximal_radius_cap_m":THUMB_PROXIMAL_RADIUS_CAP_M,
        "webbing_vertex_count":len(webbing),"proximal_transition_vertex_count":len(proximal_transition),"inter_joint_transition_vertex_count":len(inter_joint_transition),
        "transition_vertex_count":len(transition),"webbing_pairs":webbing_pairs,
        "webbing_vertex_indices":sorted(webbing),"transition_vertex_indices":sorted(transition),
        "preserved_nonfinger_rows":preserved,"expected_preserved_nonfinger_rows":len(body.vertices)-len(overridden),
        "bind_reconstruction_max_error_m":bind_error,"max_influences":max(active_counts),"mean_influences":sum(active_counts)/len(active_counts),"validation":validation,
        "truth":{
            "shared_body_skin_preserved_outside_classified_finger_root_zone":preserved==len(body.vertices)-len(overridden),
            "source_grounded_segments":True,"explicit_webbing_transition":True,"thumb_root_has_dedicated_source_neighborhood":True,
            "production_finger_skinning_claim":False,"corrective_shapes_claim":False,
            "notes":[
                "v0.2 changes weights only; the 53-joint source-grounded skeleton, canonical body mesh and v0.7 contact solution remain separate state.",
                "Ambiguous proximal space between the four long fingers is no longer forced to one nearest digit. Hand plus both adjacent proximal joints share the transition with at most three active influences.",
                "The thumb proximal source bone gets a bounded 22% radius expansion because its oblique palm exit was underrepresented by the long-finger neighborhood rule; the rest of the classifier remains tighter than v0.1.",
                "The wider transition zones are a deformation hypothesis and require same-pose webbing distortion metrics plus Godot hands-close evidence before promotion."
            ],
        },
    }
    return result,evidence
