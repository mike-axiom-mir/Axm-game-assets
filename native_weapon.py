#!/usr/bin/env python3
"""AXM deterministic semantic rifle construction + socket state v0.4."""
from __future__ import annotations

from dataclasses import dataclass
from math import cos, sin, sqrt

from native_attachment import Socket
from native_geometry import Mesh, bounds, combine, topology_report, triangulate
from native_modeling import make_chamfered_box, make_cylinder, place
from native_orientation import winding_report


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


def _x_cylinder(radius: float, length: float, *, segments: int, name: str, x: float, y: float = 0.0, z: float = 0.0) -> Mesh:
    mesh = _rotate_y(make_cylinder(radius, length, segments=segments, name=name), 1.5707963267948966)
    return place(mesh, x=x, y=y, z=z)


def sentinel_rifle(*, name: str = "sentinel_rifle") -> WeaponAsset:
    components: dict[str, Mesh] = {}

    # Core receiver silhouette. These are separate reconstructable shells rather
    # than one anonymous block so future material/LOD organs can address them.
    components["receiver"] = make_chamfered_box(0.50, 0.155, 0.105, 0.025, name="receiver")
    components["lower_receiver"] = place(
        make_chamfered_box(0.30, 0.090, 0.098, 0.016, name="lower_receiver"),
        x=-0.055,
        y=-0.100,
    )
    components["receiver_front_block"] = place(
        make_chamfered_box(0.145, 0.126, 0.116, 0.018, name="receiver_front_block"),
        x=0.235,
        y=0.005,
    )
    components["receiver_side_plate_left"] = place(
        make_chamfered_box(0.215, 0.075, 0.012, 0.007, name="receiver_side_plate_left"),
        x=0.055,
        y=0.015,
        z=0.061,
    )
    components["receiver_side_plate_right"] = place(
        make_chamfered_box(0.215, 0.075, 0.012, 0.007, name="receiver_side_plate_right"),
        x=0.055,
        y=0.015,
        z=-0.061,
    )
    components["ejection_port_plate"] = place(
        make_chamfered_box(0.105, 0.045, 0.010, 0.005, name="ejection_port_plate"),
        x=0.090,
        y=0.030,
        z=-0.071,
    )

    # Stock is built as a layered buttstock instead of a single brick.
    components["stock_core"] = place(
        make_chamfered_box(0.34, 0.112, 0.088, 0.024, name="stock_core"),
        x=-0.39,
        y=-0.005,
    )
    stock_spine = _rotate_z(
        make_chamfered_box(0.315, 0.054, 0.068, 0.012, name="stock_spine"),
        -0.11,
    )
    components["stock_spine"] = place(stock_spine, x=-0.385, y=0.070)
    stock_lower = _rotate_z(
        make_chamfered_box(0.275, 0.048, 0.062, 0.011, name="stock_lower_brace"),
        0.19,
    )
    components["stock_lower_brace"] = place(stock_lower, x=-0.405, y=-0.078)
    components["cheek_rest"] = place(
        make_chamfered_box(0.245, 0.040, 0.082, 0.010, name="cheek_rest"),
        x=-0.365,
        y=0.102,
    )
    components["stock_pad"] = place(
        make_chamfered_box(0.055, 0.158, 0.108, 0.014, name="stock_pad"),
        x=-0.585,
        y=-0.004,
    )
    components["rear_sling_mount"] = place(
        make_chamfered_box(0.045, 0.050, 0.038, 0.008, name="rear_sling_mount"),
        x=-0.545,
        y=-0.105,
    )

    # Handguard and barrel layers.
    components["handguard_shell"] = place(
        make_chamfered_box(0.285, 0.112, 0.126, 0.018, name="handguard_shell"),
        x=0.355,
        y=0.020,
    )
    components["handguard_left_rail"] = place(
        make_chamfered_box(0.235, 0.030, 0.022, 0.005, name="handguard_left_rail"),
        x=0.355,
        y=0.018,
        z=0.078,
    )
    components["handguard_right_rail"] = place(
        make_chamfered_box(0.235, 0.030, 0.022, 0.005, name="handguard_right_rail"),
        x=0.355,
        y=0.018,
        z=-0.078,
    )
    components["handguard_bottom_rail"] = place(
        make_chamfered_box(0.225, 0.022, 0.072, 0.005, name="handguard_bottom_rail"),
        x=0.345,
        y=-0.050,
    )

    components["barrel"] = _x_cylinder(0.021, 0.55, segments=24, name="barrel", x=0.570, y=0.020)
    components["barrel_shroud"] = _x_cylinder(0.039, 0.29, segments=20, name="barrel_shroud", x=0.390, y=0.020)
    components["barrel_collar_rear"] = _x_cylinder(0.047, 0.030, segments=20, name="barrel_collar_rear", x=0.255, y=0.020)
    components["barrel_collar_front"] = _x_cylinder(0.045, 0.030, segments=20, name="barrel_collar_front", x=0.505, y=0.020)
    components["muzzle_device"] = _x_cylinder(0.037, 0.105, segments=20, name="muzzle_device", x=0.850, y=0.020)
    components["muzzle_ring_rear"] = _x_cylinder(0.044, 0.025, segments=20, name="muzzle_ring_rear", x=0.805, y=0.020)
    components["muzzle_ring_front"] = _x_cylinder(0.043, 0.022, segments=20, name="muzzle_ring_front", x=0.895, y=0.020)
    for side_index, z in enumerate((-0.050, 0.050)):
        components[f"muzzle_side_lug_{side_index}"] = place(
            make_chamfered_box(0.055, 0.025, 0.018, 0.004, name=f"muzzle_side_lug_{side_index}"),
            x=0.850,
            y=0.020,
            z=z,
        )

    # Top rail: a structural spine plus individually modeled teeth so the
    # close-up silhouette carries meaningful frequency rather than smooth slab.
    components["upper_rail_spine"] = place(
        make_chamfered_box(0.43, 0.022, 0.072, 0.005, name="upper_rail_spine"),
        x=0.070,
        y=0.101,
    )
    rail_start = -0.125
    for index in range(11):
        x = rail_start + index * 0.039
        components[f"upper_rail_tooth_{index:02d}"] = place(
            make_chamfered_box(0.021, 0.018, 0.080, 0.004, name=f"upper_rail_tooth_{index:02d}"),
            x=x,
            y=0.119,
        )

    # Primary hand controls and magazine assembly.
    grip = _rotate_z(make_chamfered_box(0.075, 0.19, 0.082, 0.012, name="primary_grip"), -0.18)
    components["primary_grip"] = place(grip, x=-0.145, y=-0.145)
    components["primary_grip_cap"] = place(
        make_chamfered_box(0.082, 0.027, 0.088, 0.006, name="primary_grip_cap"),
        x=-0.162,
        y=-0.242,
    )
    components["foregrip"] = place(
        make_chamfered_box(0.065, 0.145, 0.070, 0.012, name="foregrip"),
        x=0.300,
        y=-0.125,
    )
    components["foregrip_cap"] = place(
        make_chamfered_box(0.073, 0.026, 0.078, 0.006, name="foregrip_cap"),
        x=0.300,
        y=-0.205,
    )
    magazine = _rotate_z(make_chamfered_box(0.105, 0.245, 0.085, 0.018, name="magazine"), 0.10)
    components["magazine"] = place(magazine, x=-0.015, y=-0.190)
    mag_base = _rotate_z(make_chamfered_box(0.118, 0.032, 0.094, 0.008, name="magazine_base"), 0.10)
    components["magazine_base"] = place(mag_base, x=-0.028, y=-0.318)
    components["magazine_feed_block"] = place(
        make_chamfered_box(0.115, 0.045, 0.092, 0.009, name="magazine_feed_block"),
        x=-0.002,
        y=-0.085,
    )

    # Trigger/guard is intentionally made from several separate closed parts;
    # it reads as a control cluster without pretending we have boolean cutouts.
    components["trigger_guard_floor"] = place(
        make_chamfered_box(0.125, 0.018, 0.060, 0.004, name="trigger_guard_floor"),
        x=-0.105,
        y=-0.143,
    )
    components["trigger_guard_front"] = place(
        make_chamfered_box(0.018, 0.060, 0.060, 0.004, name="trigger_guard_front"),
        x=-0.045,
        y=-0.118,
    )
    components["trigger_guard_rear"] = place(
        make_chamfered_box(0.018, 0.056, 0.060, 0.004, name="trigger_guard_rear"),
        x=-0.168,
        y=-0.118,
    )
    trigger = _rotate_z(make_chamfered_box(0.016, 0.052, 0.022, 0.003, name="trigger"), -0.20)
    components["trigger"] = place(trigger, x=-0.110, y=-0.118)

    # Optic stack and backup sights.
    components["optic_base"] = place(
        make_chamfered_box(0.16, 0.032, 0.075, 0.008, name="optic_base"),
        x=0.015,
        y=0.145,
    )
    components["optic_body"] = _x_cylinder(0.034, 0.14, segments=20, name="optic_body", x=0.015, y=0.183)
    components["optic_front_ring"] = _x_cylinder(0.043, 0.026, segments=20, name="optic_front_ring", x=0.078, y=0.183)
    components["optic_rear_ring"] = _x_cylinder(0.041, 0.024, segments=20, name="optic_rear_ring", x=-0.050, y=0.183)
    components["rear_sight"] = place(
        make_chamfered_box(0.030, 0.065, 0.070, 0.006, name="rear_sight"),
        x=-0.150,
        y=0.151,
    )
    components["front_sight"] = place(
        make_chamfered_box(0.026, 0.072, 0.064, 0.006, name="front_sight"),
        x=0.485,
        y=0.132,
    )

    components["side_module"] = place(
        make_chamfered_box(0.118, 0.052, 0.028, 0.007, name="side_module"),
        x=0.160,
        y=0.035,
        z=-0.082,
    )
    components["side_module_cap"] = place(
        make_chamfered_box(0.032, 0.061, 0.034, 0.007, name="side_module_cap"),
        x=0.220,
        y=0.035,
        z=-0.082,
    )

    # Repeated side fasteners add deterministic semantic detail. Default
    # cylinder axis is Z, which is appropriate for side-mounted hardware.
    fastener_xs = (-0.175, -0.060, 0.065, 0.185, 0.315, 0.420)
    for side_name, z in (("left", 0.068), ("right", -0.068)):
        for index, x in enumerate(fastener_xs):
            components[f"fastener_{side_name}_{index:02d}"] = place(
                make_cylinder(0.008, 0.012, segments=12, name=f"fastener_{side_name}_{index:02d}"),
                x=x,
                y=0.018 if x < 0.23 else 0.012,
                z=z,
            )

    mesh = combine(components.values(), name=name)
    half = sqrt(0.5)
    sockets = {
        "primary_grip": Socket("primary_grip", (-0.145, -0.175, 0.0)),
        "support_grip": Socket("support_grip", (0.300, -0.155, 0.0)),
        # Weapon geometry points down +X. Rotate socket-local +Z to +X so VFX
        # and projectile proposal organs inherit an explicit forward direction.
        "muzzle": Socket("muzzle", (0.910, 0.020, 0.0), (0.0, half, 0.0, half)),
        "magazine": Socket("magazine", (-0.028, -0.330, 0.0)),
        "optic": Socket("optic", (0.015, 0.183, 0.0)),
        "ejection": Socket("ejection", (0.090, 0.030, -0.078)),
    }
    features = list(components.keys()) + [f"socket:{socket_name}" for socket_name in sockets]
    return WeaponAsset(name, mesh, components, sockets, features)


def validate_weapon(asset: WeaponAsset) -> dict[str, object]:
    failures: list[str] = []
    component_reports: dict[str, object] = {}
    winding_reports: dict[str, object] = {}
    for component_name, mesh in asset.components.items():
        report = topology_report(mesh)
        component_reports[component_name] = report
        if not report["closed_two_manifold_candidate"]:
            failures.append(f"component {component_name} is not a closed manifold candidate")
        winding = winding_report(mesh)
        winding_reports[component_name] = winding
        if winding["status"] != "pass":
            failures.append(
                f"component {component_name} has unsafe winding classification {winding['classification']}"
            )

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
        "semantic_features": len(asset.semantic_features),
        "sockets": sorted(asset.sockets),
        "triangles": len(triangulate(asset.mesh).faces),
        "bounds": [list(lo), list(hi)],
        "component_reports": component_reports,
        "winding_reports": winding_reports,
        "truth": "Semantic procedural rifle fixture with layered close-inspection geometry. Closed component shells must prove outward winding so a valid import cannot hide an inside-out/backface-culling defect. Geometry density is semantic source detail, not a production weapon-art claim.",
    }
