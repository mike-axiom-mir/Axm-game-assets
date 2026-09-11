#!/usr/bin/env python3
"""Dependency-free dual-quaternion skinning for rigid skeletal transforms.

This is a focused deformation kernel, not a replacement for the existing LBS
path. DQS is useful where blended rotations collapse volume, especially finger,
wrist and shoulder bends. The implementation accepts the same four-influence
SkinWeights and Skeleton state as native_skin.py, requires unit joint scale, and
keeps canonical mesh/skeleton state unchanged.
"""
from __future__ import annotations

from math import sqrt

from native_geometry import Mesh, Vec3
from native_skin import Quat, Skeleton, SkinWeights, normalize_quaternion, validate_skin_weights, validate_skeleton

DQ = tuple[Quat,Quat]


def _qmul(a:Quat,b:Quat)->Quat:
    ax,ay,az,aw=a;bx,by,bz,bw=b
    return (
        aw*bx+ax*bw+ay*bz-az*by,
        aw*by-ax*bz+ay*bw+az*bx,
        aw*bz+ax*by-ay*bx+az*bw,
        aw*bw-ax*bx-ay*by-az*bz,
    )


def _qconj(q:Quat)->Quat:
    return (-q[0],-q[1],-q[2],q[3])


def _qdot(a:Quat,b:Quat)->float:
    return sum(x*y for x,y in zip(a,b))


def _qscale(q:Quat,s:float)->Quat:
    return tuple(v*s for v in q)  # type: ignore[return-value]


def _qadd(a:Quat,b:Quat)->Quat:
    return tuple(x+y for x,y in zip(a,b))  # type: ignore[return-value]


def _rotate(q:Quat,p:Vec3)->Vec3:
    q=normalize_quaternion(q)
    r=_qmul(_qmul(q,(p[0],p[1],p[2],0.0)),_qconj(q))
    return r[0],r[1],r[2]


def _global_rt(skeleton:Skeleton)->list[tuple[Quat,Vec3]]:
    report=validate_skeleton(skeleton)
    if report["status"]!="pass":raise ValueError(f"invalid skeleton: {report}")
    cache:list[tuple[Quat,Vec3]|None]=[None]*len(skeleton.joints)
    def resolve(index:int)->tuple[Quat,Vec3]:
        cached=cache[index]
        if cached is not None:return cached
        joint=skeleton.joints[index]
        if any(abs(float(v)-1.0)>1e-9 for v in joint.scale):
            raise ValueError("dual-quaternion skinning requires unit joint scale")
        local_r=normalize_quaternion(joint.rotation)
        if joint.parent is None:
            result=(local_r,joint.translation)
        else:
            parent_r,parent_t=resolve(joint.parent)
            rotated=_rotate(parent_r,joint.translation)
            result=(normalize_quaternion(_qmul(parent_r,local_r)),(parent_t[0]+rotated[0],parent_t[1]+rotated[1],parent_t[2]+rotated[2]))
        cache[index]=result
        return result
    return [resolve(i) for i in range(len(skeleton.joints))]


def _rigid_skin_dq(bind_rt:tuple[Quat,Vec3],pose_rt:tuple[Quat,Vec3])->DQ:
    bind_r,bind_t=bind_rt;pose_r,pose_t=pose_rt
    real=normalize_quaternion(_qmul(pose_r,_qconj(bind_r)))
    rotated_bind=_rotate(real,bind_t)
    translation=(pose_t[0]-rotated_bind[0],pose_t[1]-rotated_bind[1],pose_t[2]-rotated_bind[2])
    dual=_qscale(_qmul((translation[0],translation[1],translation[2],0.0),real),0.5)
    return real,dual


def _blend_dq(rows:list[tuple[DQ,float]])->DQ:
    active=[(dq,float(weight)) for dq,weight in rows if weight>0.0]
    if not active:raise ValueError("dual-quaternion blend has no active influences")
    reference=active[0][0][0]
    real=(0.0,0.0,0.0,0.0);dual=(0.0,0.0,0.0,0.0)
    for (qr,qd),weight in active:
        sign=-1.0 if _qdot(qr,reference)<0.0 else 1.0
        real=_qadd(real,_qscale(qr,weight*sign))
        dual=_qadd(dual,_qscale(qd,weight*sign))
    norm=sqrt(_qdot(real,real))
    if norm<=1e-12:raise ValueError("dual-quaternion real blend collapsed")
    real=_qscale(real,1.0/norm)
    dual=_qscale(dual,1.0/norm)
    # Project dual part orthogonal to real part so the normalized pair remains a
    # rigid dual quaternion after linear blending.
    dual=_qadd(dual,_qscale(real,-_qdot(real,dual)))
    return real,dual


def _dq_transform(dq:DQ,p:Vec3)->Vec3:
    real,dual=dq
    rotated=_rotate(real,p)
    tq=_qmul(dual,_qconj(real))
    translation=(2.0*tq[0],2.0*tq[1],2.0*tq[2])
    return rotated[0]+translation[0],rotated[1]+translation[1],rotated[2]+translation[2]


def dual_quaternion_skin_vertices(mesh:Mesh,weights:SkinWeights,bind_skeleton:Skeleton,posed_skeleton:Skeleton)->list[Vec3]:
    if len(bind_skeleton.joints)!=len(posed_skeleton.joints):raise ValueError("bind and posed skeleton joint counts differ")
    validation=validate_skin_weights(weights,vertex_count=len(mesh.vertices),joint_count=len(bind_skeleton.joints))
    if validation["status"]!="pass":raise ValueError(f"invalid skin weights: {validation}")
    bind_rt=_global_rt(bind_skeleton);pose_rt=_global_rt(posed_skeleton)
    joint_dq=[_rigid_skin_dq(b,p) for b,p in zip(bind_rt,pose_rt)]
    output=[]
    for point,joints,values in zip(mesh.vertices,weights.joints,weights.weights):
        blended=_blend_dq([(joint_dq[joint],weight) for joint,weight in zip(joints,values) if weight>0.0])
        output.append(_dq_transform(blended,point))
    return output


def dual_quaternion_skin_mesh(mesh:Mesh,weights:SkinWeights,bind_skeleton:Skeleton,posed_skeleton:Skeleton,*,name:str|None=None)->Mesh:
    return Mesh(name or f"{mesh.name}_dqs",dual_quaternion_skin_vertices(mesh,weights,bind_skeleton,posed_skeleton),list(mesh.faces))
