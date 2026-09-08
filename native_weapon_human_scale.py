#!/usr/bin/env python3
"""Human-scale Sentinel rifle dimensional redesign v0.5.

The earlier semantic rifle fixture is retained as historical source evidence,
but real character-contact rendering showed it was roughly 1.5 m long against
a 1.82 m human and visually dominated the entire torso/face. This module keeps
its semantic component breakdown, sockets, material grouping compatibility and
triangle detail while authoring a new canonical-size delivery state.

This is not a runtime scale trick. The scaled component coordinates and socket
positions become the authored source state returned by this constructor. A
contact/engine consumer should still place this asset at scale 1.0.
"""
from __future__ import annotations

from math import sqrt

from native_attachment import Socket
from native_geometry import Mesh, bounds, combine, scale, triangulate
from native_weapon import WeaponAsset, sentinel_rifle, validate_weapon

SCHEMA = "axm.game-assets.sentinel-rifle-human-scale.v0.5"
DESIGN_SCALE = (0.64, 0.82, 0.82)


def _scale_point(point: tuple[float, float, float]) -> tuple[float, float, float]:
    return (
        point[0] * DESIGN_SCALE[0],
        point[1] * DESIGN_SCALE[1],
        point[2] * DESIGN_SCALE[2],
    )


def sentinel_rifle_human_scale(*, name: str = "sentinel_rifle_human_scale_v0_5") -> WeaponAsset:
    legacy = sentinel_rifle(name="sentinel_rifle_v0_4_legacy_source")
    components: dict[str, Mesh] = {
        component_name: scale(mesh, DESIGN_SCALE, name=component_name)
        for component_name, mesh in legacy.components.items()
    }
    sockets = {
        socket_name: Socket(
            socket.name,
            _scale_point(socket.position),
            socket.rotation,
        )
        for socket_name, socket in legacy.sockets.items()
    }
    mesh = combine(components.values(), name=name)
    features = list(legacy.semantic_features) + [
        "design:human_scale_v0.5",
        "legacy_source:sentinel_rifle_v0.4",
        f"design_scale:{DESIGN_SCALE[0]:.3f},{DESIGN_SCALE[1]:.3f},{DESIGN_SCALE[2]:.3f}",
    ]
    return WeaponAsset(name, mesh, components, sockets, features)


def human_scale_weapon_evidence(asset: WeaponAsset | None = None) -> dict[str, object]:
    weapon = asset or sentinel_rifle_human_scale()
    report = validate_weapon(weapon)
    lo, hi = bounds(weapon.mesh)
    size = [hi[axis] - lo[axis] for axis in range(3)]
    primary = weapon.sockets["primary_grip"].position
    support = weapon.sockets["support_grip"].position
    grip_span = sqrt(sum((support[axis] - primary[axis]) ** 2 for axis in range(3)))
    return {
        "schema": SCHEMA,
        "validation": report,
        "design_scale": list(DESIGN_SCALE),
        "bounds": {"min": list(lo), "max": list(hi), "size": size},
        "overall_length_m": size[0],
        "grip_socket_separation_m": grip_span,
        "triangles": len(triangulate(weapon.mesh).faces),
        "component_count": len(weapon.components),
        "socket_count": len(weapon.sockets),
        "truth": {
            "runtime_scale_required": False,
            "runtime_scale": [1.0, 1.0, 1.0],
            "legacy_rifle_deleted": False,
            "production_weapon_art_claim": False,
            "notes": [
                "Real shared-rig Godot contact evidence showed the legacy semantic fixture was physically oversized for the 1.82 m Sentinel body.",
                "v0.5 authors smaller component coordinates and socket coordinates directly while preserving semantic parts/material compatibility.",
                "The barrel axis is compressed more strongly than height/depth so the result reads as a substantial combat rifle rather than a uniformly miniaturized prop.",
                "Close-up manufacturing quality remains a separate visual gate."
            ],
        },
    }


if __name__ == "__main__":
    import json
    weapon = sentinel_rifle_human_scale()
    print(json.dumps(human_scale_weapon_evidence(weapon), indent=2))
