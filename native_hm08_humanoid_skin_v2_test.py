#!/usr/bin/env python3

from native_hm08_humanoid_rig import build_hm08_humanoid_skeleton, build_hm08_skin_weights, derive_hm08_rig_landmarks
from native_hm08_humanoid_skin_v2 import build_hm08_skin_weights_v2
from native_hm08_undersuit import _load_identity_body
from native_skin import skin_vertices


def max_error(a,b):
    return max(sum((x-y)**2 for x,y in zip(pa,pb))**0.5 for pa,pb in zip(a,b))


def run() -> None:
    body, _uv, _state = _load_identity_body()
    landmarks=derive_hm08_rig_landmarks(body)
    skeleton,_evidence,indices=build_hm08_humanoid_skeleton(body)
    base,_base_evidence=build_hm08_skin_weights(body,skeleton,landmarks,indices)
    first,first_evidence=build_hm08_skin_weights_v2(body,skeleton,landmarks,indices)
    second,second_evidence=build_hm08_skin_weights_v2(body,skeleton,landmarks,indices)
    assert first_evidence==second_evidence
    assert first.joints==second.joints and first.weights==second.weights
    assert first_evidence["schema"]=="axm.game-assets.hm08-humanoid-skin.v0.2"
    assert first_evidence["base_skin_schema"]=="axm.game-assets.hm08-humanoid-skin.v0.1"
    assert first_evidence["validation"]["status"]=="pass"
    assert first_evidence["max_influences"]<=4
    assert first_evidence["overridden_arm_vertices"]["right"]>1000,first_evidence
    assert first_evidence["overridden_arm_vertices"]["left"]>1000,first_evidence
    assert first_evidence["rigid_hand_vertices"]["right"]>500,first_evidence
    assert first_evidence["rigid_hand_vertices"]["left"]>500,first_evidence
    assert first_evidence["zone_counts"]["upper"]>100
    assert first_evidence["zone_counts"]["forearm"]>100
    assert first_evidence["zone_counts"]["elbow"]>100
    assert first_evidence["zone_counts"]["wrist"]>50
    assert first_evidence["truth"]["shared_skeleton_preserved"] is True
    assert first_evidence["truth"]["non_arm_base_weights_preserved"] is True
    assert first_evidence["truth"]["production_skinning_claim"] is False
    assert first_evidence["truth"]["finger_chain_claim"] is False

    bind_vertices=skin_vertices(body,first,skeleton,skeleton)
    assert max_error(body.vertices,bind_vertices)<1e-9

    changed_rows=sum(1 for a,b,c,d in zip(base.joints,base.weights,first.joints,first.weights) if a!=c or b!=d)
    assert changed_rows>2000,changed_rows
    print("HM08 HUMANOID SEGMENT SKIN V0.2 PASS",{
        "changed_rows":changed_rows,
        "overridden":first_evidence["overridden_arm_vertices"],
        "rigid_hands":first_evidence["rigid_hand_vertices"],
        "zones":first_evidence["zone_counts"],
        "mean_influences":first_evidence["mean_influences"],
    })


if __name__=="__main__":
    run()
