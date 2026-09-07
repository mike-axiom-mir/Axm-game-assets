#!/usr/bin/env python3
"""AXM deterministic semantic rifle construction + socket state v0.2."""
from __future__ import annotations

from dataclasses import dataclass
from math import cos, sin, sqrt

from native_attachment import Socket
from native_geometry import Mesh, bounds, combine, topology_report, triangulate
from native_modeling import make_chamfered_box, make_cylinder, place


@dataclass(slots=True)
class WeaponAsset:
    name: str
    mesh: Mesh
    components: dict[str, Mesh]
    sockets: dict[str, Socket]
    semantic_features: list[str]


def _rotate_y(mesh: Mesh, angle: float, *, name: str | None = None) -> Mesh:
    c, s = cos(angle), sin(angle)
    vertices = [(x * c + z * s, y, -x * s + z * c) for x, y, z in mesh.vertices]
    return Mesh(name or mesh.name, vertices, list(mesh.faces))


def _rotate_z(mesh: Mesh, angle: float, *, name: str | None = None) -> Mesh:
    c, s = cos(angle), sin(angle)
    vertices = [(x * c - y * s, x * s + y * c, z) for x, y, z in mesh.vertices]
    return Mesh(name or mesh.name, vertices, list(mesh.faces))


def sentinel_rifle(*, name: str = "sentinel_rifle") -> WeaponAsset:
    components: dict[str, Mesh] = {}
    components["receiver"] = make_chamfered_box(0.50, 0.155, 0.105, 0.025, name="receiver")
    components["upper_rail"] = place(make_chamfered_box(0.36, 0.026, 0.072, 0.006, name="upper_rail"), x=0.035, y=0.093)
    components["stock"] = place(make_chamfered_box(0.34, 0.125, 0.092, 0.025, name="stock"), x=-0.39, y=-0.005)
    components["stock_pad"] = place(make_chamfered_box(0.055, 0.145, 0.105, 0.014, name="stock_pad"), x=-0.585, y=-0.004)

    barrel = _rotate_y(make_cylinder(0.024, 0.55, segments=20, name="barrel"), 1.5707963267948966)
    components["barrel"] = place(barrel, x=0.505, y=0.020)
    shroud = _rotate_y(make_cylinder(0.042, 0.31, segments=16, name="barrel_shroud"), 1.5707963267948966)
    components["barrel_shroud"] = place(shroud, x=0.365, y=0.020)
    muzzle = _rotate_y(make_cylinder(0.036, 0.10, segments=16, name="muzzle_device"), 1.5707963267948966)
    components["muzzle_device"] = place(muzzle, x=0.825, y=0.020)

    grip = _rotate_z(make_chamfered_box(0.075, 0.19, 0.082, 0.012, name="primary_grip"), -0.18)
    components["primary_grip"] = place(grip, x=-0.145, y=-0.145)
    components["foregrip"] = place(make_chamfered_box(0.065, 0.14, 0.070, 0.012, name="foregrip"), x=0.265, y=-0.125)
    magazine = _rotate_z(make_chamfered_box(0.105, 0.245, 0.085, 0.018, name="magazine"), 0.10)
    components["magazine"] = place(magazine, x=-0.015, y=-0.190)

    components["optic_base"] = place(make_chamfered_box(0.16, 0.032, 0.075, 0.008, name="optic_base"), x=0.015, y=0.126)
    optic = _rotate_y(make_cylinder(0.034, 0.14, segments=16, name="optic"), 1.5707963267948966)
    components["optic"] = place(optic, x=0.015, y=0.165)
    components["side_module"] = place(make_chamfered_box(0.105, 0.052, 0.026, 0.007, name="side_module"), x=0.165, y=0.035, z=-0.067)

    mesh = combine(components.values(), name=name)
    half = sqrt(0.5)
    sockets = {
        "primary_grip": Socket("primary_grip", (-0.145, -0.175, 0.0)),
        "support_grip": Socket("support_grip", (0.265, -0.155, 0.0)),
        # Weapon geometry points down +X. Rotate socket-local +Z to +X so VFX
        # and projectile proposal organs inherit an explicit forward direction.
        "muzzle": Socket("muzzle", (0.875, 0.020, 0.0), (0.0, half, 0.0, half)),
        "magazine": Socket("magazine", (-0.015, -0.305, 0.0)),
        "optic": Socket("optic", (0.015, 0.165, 0.0)),
        "ejection": Socket("ejection", (0.105, 0.045, -0.060)),
    }
    features = list(components.keys()) + [f"socket:{socket_name}" for socket_name in sockets]
    return WeaponAsset(name, mesh, components, sockets, features)


def validate_weapon(asset: WeaponAsset) -> dict[str, object]:
    failures = []
    component_reports = {}
    for component_name, mesh in asset.components.items():
        report = topology_report(mesh)
        component_reports[component_name] = report
        if not report["closed_two_manifold_candidate"]:
            failures.append(f"component {component_name} is not a closed manifold candidate")
    required_sockets = {"primary_grip", "support_grip", "muzzle", "magazine"}
    missing = sorted(required_sockets - set(asset.sockets))
    if missing:
        failures.append(f"missing required sockets {missing}")
    lo, hi = bounds(asset.mesh)
    margin = 0.15
    for socket_name, socket in asset.sockets.items():
        point = socket.position
        if any(point[axis] < lo[axis] - margin or point[axis] > hi[axis] + margin for axis in range(3)):
            failures.append(f"socket {socket_name} lies implausibly far outside weapon bounds")
    return {
        "status": "pass" if not failures else "fail",
        "failures": failures,
        "components": len(asset.components),
        "sockets": sorted(asset.sockets),
        "triangles": len(triangulate(asset.mesh).faces),
        "bounds": [list(lo), list(hi)],
        "component_reports": component_reports,
        "truth": "Semantic procedural rifle fixture. It proves layered geometry/socket state, not final weapon art, ergonomics or ballistics.",
    }
