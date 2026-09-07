#!/usr/bin/env python3
"""AXM native Sentinel rifle + two-hand contact proof v0.2."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from native_animation import AnimationClip, AnimationTrack
from native_attachment import TwoHandAttachment, sample_two_hand_contact
from native_gltf import write_gltf
from native_pbr import PaintedMetalSpec, write_painted_metal
from native_preview import write_preview
from native_skin import Joint, Skeleton
from native_uv import box_project, validate_uv
from native_weapon import sentinel_rifle, validate_weapon

SCHEMA = "axm.game-assets.native-weapon-proof.v0.2"


def _sha(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def build_weapon_proof(output: str | Path, *, texture_size: int = 64, preview_size: int = 96, seed: int = 8801) -> dict[str, object]:
    root = Path(output)
    root.mkdir(parents=True, exist_ok=True)
    weapon = sentinel_rifle()
    weapon_report = validate_weapon(weapon)
    if weapon_report["status"] != "pass":
        raise ValueError(f"weapon geometry failed: {weapon_report}")
    uv = box_project(weapon.mesh)
    uv_report = validate_uv(weapon.mesh, uv)
    if uv_report["status"] != "pass":
        raise ValueError(f"weapon UV failed: {uv_report}")

    # Engine screenshot v0.1 showed the generic metal preset reading too bright
    # and chrome-like under proof lighting. This recipe keeps the same native
    # deterministic PBR mechanism but authors a darker, rougher coated weapon
    # surface with less exposed metal. It is still not a measured scan.
    weapon_material_spec = PaintedMetalSpec(
        paint_rgb=(28, 36, 41),
        metal_rgb=(72, 78, 82),
        paint_roughness=0.64,
        metal_roughness=0.40,
        wear=0.16,
        scratches=24,
        grain_scale=34.0,
    )
    material = write_painted_metal(
        root / "textures",
        size=texture_size,
        seed=seed,
        spec=weapon_material_spec,
    )
    delivery = write_gltf(weapon.mesh, uv, root, material_name="AXM_Native_Weapon_CoatedMetal")
    preview = write_preview(weapon.mesh, root / "preview", size=preview_size)

    primary = weapon.sockets["primary_grip"].position
    support = weapon.sockets["support_grip"].position
    delta = tuple(support[axis] - primary[axis] for axis in range(3))
    # Fixture hands are arranged to exactly match the weapon's two authored
    # grip sockets. The weapon is anchored to the right hand by primary grip.
    skeleton = Skeleton([
        Joint("root"),
        Joint("right_hand", parent=0, translation=(0.30, 1.0, 0.0)),
        Joint("left_hand", parent=0, translation=(0.30 + delta[0], 1.0 + delta[1], delta[2])),
    ])
    attachment = TwoHandAttachment(
        primary_joint=1,
        support_joint=2,
        primary_socket=weapon.sockets["primary_grip"],
        support_socket=weapon.sockets["support_grip"],
    )
    carry = AnimationClip("rifle_carry", [
        AnimationTrack(0, "translation", [0.0, 1.0], [(0.0, 0.0, 0.0), (0.28, 0.08, -0.14)])
    ])
    contact = sample_two_hand_contact(skeleton, carry, attachment, [0.0, 0.25, 0.5, 0.75, 1.0])

    manifest: dict[str, object] = {
        "schema": SCHEMA,
        "asset": weapon.name,
        "weapon": weapon_report,
        "sockets": {name: {"position": list(socket.position), "rotation": list(socket.rotation)} for name, socket in sorted(weapon.sockets.items())},
        "uv": uv_report,
        "material": material,
        "delivery": delivery,
        "preview": preview,
        "two_hand_contact": contact,
        "acceptance": {
            "weapon_state_valid": weapon_report["status"] == "pass",
            "semantic_component_density": int(weapon_report["components"]) >= 45,
            "closed_shell_winding_safe": all(
                item["status"] == "pass" for item in weapon_report["winding_reports"].values()
            ),
            "required_sockets_present": {"primary_grip", "support_grip", "muzzle", "magazine"}.issubset(weapon.sockets),
            "uv_valid": uv_report["status"] == "pass",
            "gltf_structural_valid": delivery["validation"]["status"] == "pass",
            "weapon_material_identity": delivery["material_name"] == "AXM_Native_Weapon_CoatedMetal",
            "primary_contact_locked": contact["max_primary_position_error"] < 1e-8 and contact["max_primary_orientation_error_deg"] < 1e-6,
            "support_contact_locked": contact["max_support_position_error"] < 1e-8 and contact["max_support_orientation_error_deg"] < 1e-6,
            "muzzle_vfx_socket_present": "muzzle" in weapon.sockets,
        },
        "truth": {
            "production_weapon_art_claim": False,
            "ballistics_claim": False,
            "material_scan_claim": False,
            "notes": [
                "The fixture proves layered weapon geometry, delivery sockets and two-hand contact mathematics.",
                "Semantic component density is a source-detail gate, not an aesthetic-quality score.",
                "Closed component shells must prove outward winding before engine delivery.",
                "The coated-metal recipe is an authored deterministic response to real-engine evidence; it is not measured physical material data.",
                "Contact proof uses an exactly authored fixture skeleton; real Sentinel animation must independently pass the same socket-error gates.",
                "Weapon VFX/ballistics behavior is not inferred from the muzzle socket; the socket only preserves attachment state.",
            ],
        },
    }
    payload = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8")
    (root / "weapon-proof.json").write_bytes(payload)
    manifest["manifest_sha256"] = _sha(payload)
    return manifest
