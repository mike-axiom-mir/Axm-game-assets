#!/usr/bin/env python3
from math import cos, radians

from native_vfx import burst_evidence, emit_burst, muzzle_flash_emitter, sample_particle
from native_weapon import sentinel_rifle


def run() -> None:
    weapon = sentinel_rifle()
    muzzle = weapon.sockets["muzzle"]
    emitter = muzzle_flash_emitter()
    a = emit_burst(muzzle, emitter, seed=404)
    b = emit_burst(muzzle, emitter, seed=404)
    c = emit_burst(muzzle, emitter, seed=405)
    assert a == b
    assert a != c
    assert len(a) == emitter.count

    evidence = burst_evidence(muzzle, emitter, a)
    assert evidence["socket_forward"][0] > 0.999
    assert abs(evidence["socket_forward"][1]) < 1e-8
    assert abs(evidence["socket_forward"][2]) < 1e-8
    assert evidence["min_forward_dot"] >= cos(radians(emitter.cone_degrees)) - 1e-9
    assert emitter.speed_min <= evidence["speed_range_observed"][0] <= evidence["speed_range_observed"][1] <= emitter.speed_max
    assert emitter.lifetime_min <= evidence["lifetime_range_observed"][0] <= evidence["lifetime_range_observed"][1] <= emitter.lifetime_max

    start = sample_particle(a[0], 0.0)
    mid = sample_particle(a[0], a[0].lifetime * 0.5)
    end = sample_particle(a[0], a[0].lifetime * 2.0)
    assert start["normalized_age"] == 0.0 and start["alive"] is True
    assert 0.49 < mid["normalized_age"] < 0.51 and mid["alive"] is True
    assert end["normalized_age"] == 1.0 and end["alive"] is False
    assert end["color"][3] == 0.0
    print("NATIVE VFX TEST PASS", evidence)


if __name__ == "__main__":
    run()
