#!/usr/bin/env python3
from native_weapon import sentinel_rifle, validate_weapon


def run() -> None:
    weapon = sentinel_rifle()
    report = validate_weapon(weapon)
    assert report["status"] == "pass", report
    assert report["components"] >= 12
    assert report["triangles"] > 400
    assert {"primary_grip", "support_grip", "muzzle", "magazine"}.issubset(weapon.sockets)
    assert weapon.sockets["muzzle"].position[0] > weapon.sockets["support_grip"].position[0]
    assert weapon.sockets["primary_grip"].position[0] < weapon.sockets["support_grip"].position[0]
    print("NATIVE WEAPON TEST PASS", report["components"], "components", report["triangles"], "triangles", report["sockets"])


if __name__ == "__main__":
    run()
