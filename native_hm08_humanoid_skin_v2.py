#!/usr/bin/env python3
"""Bone-segment arm weighting refinement for the shared hm08 humanoid rig.

The v0.1 rig intentionally used inverse distance to joint points everywhere.
Real rifle-contact views exposed the expected failure: shoulders/elbows taper
and fold like rubber because a limb surface is not naturally partitioned by
point-distance Voronoi fields.

v0.2 preserves the shared 23-joint skeleton and the existing v0.1 weights for
all non-arm regions. Only arm neighborhoods are replaced by deterministic
bone-segment weights with explicit shoulder, elbow, wrist and rigid-hand blend
zones. No new skeleton is created.
"""
from __future__ import annotations

from math import sqrt

from native_geometry import Mesh, Vec3, bounds
from native_hm08_humanoid_rig import build_hm08_skin_weights
from native_skin import Skeleton, SkinWeights, normalize_weights, validate_skin_weights

SCHEMA = "axm.game-assets.hm08-humanoid-skin.v0.2"


def _sub(a: Vec3,b: Vec3)->Vec3:
    return a[0]-b[0],a[1]-b[1],a[2]-b[2]


def _add(a: Vec3,b: Vec3)->Vec3:
    return a[0]+b[0],a[1]+b[1],a[2]+b[2]


def _mul(a: Vec3,s: float)->Vec3:
    return a[0]*s,a[1]*s,a[2]*s


def _dot(a: Vec3,b: Vec3)->float:
    return a[0]*b[0]+a[1]*b[1]+a[2]*b[2]


def _length(a: Vec3)->float:
    return sqrt(_dot(a,a))


def _segment_distance(point: Vec3,a: Vec3,b: Vec3)->tuple[float,float,Vec3]:
    ab=_sub(b,a)
    denom=max(_dot(ab,ab),1e-12)
    t=max(0.0,min(1.0,_dot(_sub(point,a),ab)/denom))
    nearest=_add(a,_mul(ab,t))
    return _length(_sub(point,nearest)),t,nearest


def _row(*pairs: tuple[int,float])->tuple[tuple[int,int,int,int],tuple[float,float,float,float]]:
    merged: dict[int,float]={}
    for joint,weight in pairs:
        if weight>1e-12:
            merged[joint]=merged.get(joint,0.0)+weight
    ordered=sorted(merged.items(),key=lambda item:(-item[1],item[0]))[:4]
    total=sum(weight for _joint,weight in ordered)
    if total<=1e-12:
        raise ValueError("segment skin row has zero total")
    ordered=[(joint,weight/total) for joint,weight in ordered]
    while len(ordered)<4:
        ordered.append((0,0.0))
    return tuple(j for j,_w in ordered),tuple(w for _j,w in ordered)


def _smooth01(value: float)->float:
    t=max(0.0,min(1.0,value))
    return t*t*(3.0-2.0*t)


def build_hm08_skin_weights_v2(
    body: Mesh,
    skeleton: Skeleton,
    landmarks: dict[str,Vec3],
    name_to_index: dict[str,int],
)->tuple[SkinWeights,dict[str,object]]:
    base,base_evidence=build_hm08_skin_weights(body,skeleton,landmarks,name_to_index)
    lo,hi=bounds(body)
    width=hi[0]-lo[0]
    height=hi[1]-lo[1]
    half_width=width*0.5
    joints=[tuple(row) for row in base.joints]
    weights=[tuple(row) for row in base.weights]
    overridden={"left":0,"right":0}
    rigid_hands={"left":0,"right":0}
    zone_counts={"shoulder":0,"upper":0,"elbow":0,"forearm":0,"wrist":0,"hand":0}

    for side,sign in (("right",1.0),("left",-1.0)):
        clav=landmarks[f"{side}_clavicle"]
        shoulder=landmarks[f"{side}_upper_arm"]
        elbow=landmarks[f"{side}_forearm"]
        wrist=landmarks[f"{side}_hand"]
        hand_tip=landmarks[f"{side}_hand_tip"]
        j_chest=name_to_index["chest"]
        j_clav=name_to_index[f"{side}_clavicle"]
        j_upper=name_to_index[f"{side}_upper_arm"]
        j_fore=name_to_index[f"{side}_forearm"]
        j_hand=name_to_index[f"{side}_hand"]

        for index,point in enumerate(body.vertices):
            # Arms are horizontally extended in the canonical source. Require a
            # real lateral position so torso vertices near the shoulder socket
            # are not accidentally captured by the arm refinement.
            if sign*point[0] < half_width*0.20:
                continue
            d_clav,t_clav,_=_segment_distance(point,clav,shoulder)
            d_upper,t_upper,_=_segment_distance(point,shoulder,elbow)
            d_fore,t_fore,_=_segment_distance(point,elbow,wrist)
            d_hand,t_hand,_=_segment_distance(point,wrist,hand_tip)
            candidates=[
                (d_clav/0.115,"clav",t_clav,d_clav),
                (d_upper/0.105,"upper",t_upper,d_upper),
                (d_fore/0.090,"fore",t_fore,d_fore),
                (d_hand/0.105,"hand",t_hand,d_hand),
            ]
            normalized,zone,t,_distance=min(candidates,key=lambda row:(row[0],row[1]))
            if normalized>1.0:
                continue

            if zone=="clav":
                # Chest remains strong on the inner clavicle; upper arm takes
                # over only near the lateral shoulder pivot.
                outer=_smooth01((t-0.38)/0.62)
                inner=1.0-outer
                upper_share=_smooth01((t-0.72)/0.28)*0.32
                clav_share=outer*(1.0-upper_share)
                joints[index],weights[index]=_row((j_chest,inner),(j_clav,clav_share),(j_upper,upper_share))
                zone_counts["shoulder"]+=1
            elif zone=="upper":
                if t<0.20:
                    blend=_smooth01(t/0.20)
                    joints[index],weights[index]=_row((j_clav,1.0-blend),(j_upper,blend))
                    zone_counts["shoulder"]+=1
                elif t>0.76:
                    blend=_smooth01((t-0.76)/0.24)
                    joints[index],weights[index]=_row((j_upper,1.0-blend),(j_fore,blend))
                    zone_counts["elbow"]+=1
                else:
                    joints[index],weights[index]=_row((j_upper,1.0))
                    zone_counts["upper"]+=1
            elif zone=="fore":
                if t<0.22:
                    blend=_smooth01(t/0.22)
                    joints[index],weights[index]=_row((j_upper,1.0-blend),(j_fore,blend))
                    zone_counts["elbow"]+=1
                elif t>0.78:
                    blend=_smooth01((t-0.78)/0.22)
                    joints[index],weights[index]=_row((j_fore,1.0-blend),(j_hand,blend))
                    zone_counts["wrist"]+=1
                else:
                    joints[index],weights[index]=_row((j_fore,1.0))
                    zone_counts["forearm"]+=1
            else:
                # Until finger chains exist, keep the whole hand rigid on the
                # anatomical hand joint. This avoids point-weight collapse while
                # honestly retaining the lack of finger closure as a visual gap.
                joints[index],weights[index]=_row((j_hand,1.0))
                rigid_hands[side]+=1
                zone_counts["hand"]+=1
            overridden[side]+=1

    refined=normalize_weights(SkinWeights(joints,weights))
    report=validate_skin_weights(refined,vertex_count=len(body.vertices),joint_count=len(skeleton.joints))
    if report["status"]!="pass":
        raise ValueError(f"hm08 segment skin v0.2 invalid: {report}")
    active=[sum(1 for value in row if value>1e-8) for row in refined.weights]
    evidence={
        "schema":SCHEMA,
        "vertex_count":len(body.vertices),
        "joint_count":len(skeleton.joints),
        "overridden_arm_vertices":overridden,
        "rigid_hand_vertices":rigid_hands,
        "zone_counts":zone_counts,
        "max_influences":max(active),
        "mean_influences":sum(active)/len(active),
        "validation":report,
        "base_skin_schema":base_evidence["schema"],
        "truth":{
            "shared_skeleton_preserved":True,
            "non_arm_base_weights_preserved":True,
            "production_skinning_claim":False,
            "finger_chain_claim":False,
            "corrective_shapes_claim":False,
            "notes":[
                "v0.2 overrides only canonical arm neighborhoods. Torso, head and lower-body weights remain the shared v0.1 skin proposal.",
                "Influence changes are based on distance/projection along clavicle, upper-arm, forearm and hand-tip bone segments instead of inverse distance to isolated joint points.",
                "Hand vertices are deliberately rigid to the hand joint until explicit finger chains/grip closure are built. This removes mesh collapse but does not claim a convincing weapon grip."
            ],
        },
    }
    return refined,evidence
