#!/usr/bin/env python3
from math import cos,pi,sin

from native_dual_quaternion_skin import dual_quaternion_skin_vertices
from native_geometry import Mesh
from native_skin import Joint,Skeleton,SkinWeights,skin_vertices


def qz(angle:float):
    return (0.0,0.0,sin(angle*0.5),cos(angle*0.5))


def run()->None:
    # Bind reconstruction must be exact.
    mesh=Mesh("dq_fixture",[(1.0,0.0,0.0),(0.0,1.0,0.0)],[(0,1,1)])
    bind=Skeleton([Joint("root"),Joint("child",parent=0)])
    weights=SkinWeights([(0,1,0,0),(0,1,0,0)],[(0.5,0.5,0.0,0.0),(0.5,0.5,0.0,0.0)])
    reconstructed=dual_quaternion_skin_vertices(mesh,weights,bind,bind)
    assert max(sum((a-b)**2 for a,b in zip(before,after))**0.5 for before,after in zip(mesh.vertices,reconstructed))<1e-10

    # Two rigid influences with a 180-degree rotational difference are the
    # canonical LBS volume-collapse fixture: the equal matrix blend sends this
    # point to the origin, while DQS preserves radius and yields a 90-degree turn.
    posed=Skeleton([Joint("root"),Joint("child",parent=0,rotation=qz(pi))])
    lbs=skin_vertices(mesh,weights,bind,posed)
    dqs=dual_quaternion_skin_vertices(mesh,weights,bind,posed)
    lbs_radius=(lbs[0][0]**2+lbs[0][1]**2+lbs[0][2]**2)**0.5
    dqs_radius=(dqs[0][0]**2+dqs[0][1]**2+dqs[0][2]**2)**0.5
    assert lbs_radius<1e-6,(lbs,dqs)
    assert abs(dqs_radius-1.0)<1e-9,(lbs,dqs)

    # With a single active joint the two skinning methods must agree exactly.
    rigid_weights=SkinWeights([(1,0,0,0),(1,0,0,0)],[(1.0,0.0,0.0,0.0),(1.0,0.0,0.0,0.0)])
    rigid_lbs=skin_vertices(mesh,rigid_weights,bind,posed)
    rigid_dqs=dual_quaternion_skin_vertices(mesh,rigid_weights,bind,posed)
    rigid_error=max(sum((a-b)**2 for a,b in zip(x,y))**0.5 for x,y in zip(rigid_lbs,rigid_dqs))
    assert rigid_error<1e-9,(rigid_lbs,rigid_dqs)
    print("DUAL QUATERNION SKIN TEST PASS",{"lbs_collapsed_radius":lbs_radius,"dqs_preserved_radius":dqs_radius,"rigid_match_error":rigid_error})


if __name__=="__main__":
    run()
