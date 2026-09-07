#!/usr/bin/env python3
"""AXM Sentinel rifle receiver-recess variant v0.1.

Applies one evidence-driven structural receiver change on top of the canonical
semantic rifle without rewriting or deleting the known-good base constructor.
"""
from __future__ import annotations

from math import cos, pi, sin

from native_geometry import Mesh, combine
from native_modeling import make_chamfered_box, place
from native_recess import make_recessed_box, recess_report
from native_weapon import WeaponAsset, sentinel_rifle, validate_weapon


def _rotate_y(mesh: Mesh, angle: float, *, name: str | None = None) -> Mesh:
    c, s = cos(angle), sin(angle)
    vertices = [(x * c + z * s, y, -x * s + z * c) for x, y, z in mesh.vertices]
    return Mesh(name or mesh.name, vertices, list(mesh.faces))


def sentinel_rifle_recessed(*, name: str = "sentinel_rifle") -> WeaponAsset:
    asset = sentinel_rifle(name=name)

    # make_recessed_box authors its cavity on local -Z. Rotate 180 degrees
    # around Y so the cavity faces +Z, which is the close-inspection side used
    # by the retained Godot receiver camera. X also flips, so author the local
    # recess center negative to land it at +X after rotation.
    receiver = make_recessed_box(
        0.50,
        0.155,
        0.105,
        recess_width=0.175,
        recess_height=0.064,
        recess_depth=0.018,
        recess_center=(-0.075, 0.010),
        name="receiver_recessed",
    )
    receiver = _rotate_y(receiver, pi, name="receiver_recessed")
    if recess_report(receiver)["status"] != "pass":
        raise ValueError("rotated receiver recess lost structural validity")
    asset.components["receiver"] = receiver

    # The old broad left side plate hid exactly the area we need to inspect.
    # Keep the named component but shrink/move it forward so continuity and
    # provenance remain while the true cavity is allowed to read visually.
    asset.components["receiver_side_plate_left"] = place(
        make_chamfered_box(
            0.052,
            0.055,
            0.010,
            0.004,
            name="receiver_side_plate_left",
        ),
        x=0.205,
        y=0.012,
        z=0.059,
    )

    # Repurpose the existing named ejection plate as an inset accessory surface
    # inside the real cavity. It remains below the +Z outer face (0.0525 m), so
    # this cannot collapse back into the old floating-slab look.
    asset.components["ejection_port_plate"] = place(
        make_chamfered_box(
            0.135,
            0.044,
            0.006,
            0.0025,
            name="ejection_port_plate",
        ),
        x=0.075,
        y=0.010,
        z=0.038,
    )

    asset.mesh = combine(asset.components.values(), name=name)
    asset.semantic_features = list(asset.components.keys()) + [
        f"socket:{socket_name}" for socket_name in asset.sockets
    ] + ["receiver:true_recess", "receiver:inset_ejection_surface"]

    report = validate_weapon(asset)
    if report["status"] != "pass":
        raise ValueError(f"receiver recess variant failed standard weapon gates: {report}")
    return asset


def receiver_recess_variant_report(asset: WeaponAsset) -> dict[str, object]:
    receiver = asset.components.get("receiver")
    if receiver is None:
        return {"status": "fail", "failure": "missing receiver component"}
    receiver_report = recess_report(receiver)
    plate = asset.components.get("ejection_port_plate")
    plate_max_z = max((vertex[2] for vertex in plate.vertices), default=0.0) if plate else None
    receiver_max_z = max((vertex[2] for vertex in receiver.vertices), default=0.0)
    receiver_z_levels = sorted({round(vertex[2], 9) for vertex in receiver.vertices})
    return {
        "status": "pass"
        if receiver_report["status"] == "pass"
        and plate is not None
        and plate_max_z is not None
        and plate_max_z < receiver_max_z
        and 0.0345 in receiver_z_levels
        and 0.0525 in receiver_z_levels
        else "fail",
        "receiver": receiver_report,
        "receiver_z_levels": receiver_z_levels,
        "receiver_outer_visible_z": receiver_max_z,
        "ejection_plate_max_z": plate_max_z,
        "inset_clearance": receiver_max_z - plate_max_z if plate_max_z is not None else None,
        "truth": "Evidence-driven receiver variant with one true +Z cavity and an inset accessory plate. It does not claim a general boolean system or final firearm design realism.",
    }
