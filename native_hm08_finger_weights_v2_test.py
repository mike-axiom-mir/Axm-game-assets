#!/usr/bin/env python3
from native_hm08_finger_rig import build_hm08_finger_skeleton
from native_hm08_finger_weights_v2 import build_hm08_finger_skin_weights_v2
from native_hm08_undersuit import _load_identity_body


def run() -> None:
    body,_uv,_state=_load_identity_body()
    skeleton,indices,_rig=build_hm08_finger_skeleton(body)
    weights,evidence=build_hm08_finger_skin_weights_v2(body,skeleton,indices)
    assert evidence["schema"]=="axm.game-assets.hm08-finger-skin.v0.2"
    assert evidence["joint_count"]==53
    assert evidence["max_influences"]<=4
    assert evidence["minimum_vertices_per_segment"]>=10,evidence
    assert evidence["webbing_vertex_count"]>=20,evidence
    assert evidence["proximal_transition_vertex_count"]>=20,evidence
    assert evidence["transition_vertex_count"]>evidence["webbing_vertex_count"],evidence
    assert evidence["preserved_nonfinger_rows"]==evidence["expected_preserved_nonfinger_rows"],evidence
    assert evidence["bind_reconstruction_max_error_m"]<=1e-10,evidence
    assert evidence["validation"]["status"]=="pass"
    assert evidence["truth"]["explicit_webbing_transition"] is True
    assert evidence["truth"]["production_finger_skinning_claim"] is False
    assert len(weights.joints)==len(body.vertices)
    print("HM08 FINGER WEIGHTS V0.2 TEST PASS",{
        "overridden":evidence["overridden_finger_root_vertices"],
        "webbing":evidence["webbing_vertex_count"],
        "proximal_transition":evidence["proximal_transition_vertex_count"],
        "inter_joint_transition":evidence["inter_joint_transition_vertex_count"],
        "webbing_pairs":evidence["webbing_pairs"],
        "mean_influences":evidence["mean_influences"],
    })


if __name__=="__main__":
    run()
