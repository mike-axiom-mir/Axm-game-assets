"""Compatibility recovery for Kettlejack Blender foundry v0.2.

The v0.1 build correctly failed on the pinned bpy 4.3 runtime because the donor's
`export_merge_animation` keyword is not accepted by that glTF operator build.
This wrapper preserves the failed v0.1 source and replaces only the exporter
call with the exercised bpy-4.3-compatible argument set.
"""
from __future__ import annotations

import json
from pathlib import Path

import bpy

import axm_kettlejack_foundry as kj

SCHEMA = "axm.game-assets.kettlejack-blender-foundry/v0.2"


def export_compat(output: Path, arm, mesh, actions):
    blend = output / "Kettlejack_source.blend"
    bpy.ops.wm.save_as_mainfile(filepath=str(blend), check_existing=False)

    bpy.ops.object.select_all(action="DESELECT")
    arm.select_set(True)
    mesh.select_set(True)
    bpy.context.view_layer.objects.active = arm
    glb = output / "Kettlejack_game_character.glb"
    bpy.ops.export_scene.gltf(
        filepath=str(glb), export_format="GLB", use_selection=True,
        export_apply=False, export_skins=True, export_def_bones=False,
        export_animations=True, export_animation_mode="ACTIONS",
        export_anim_slide_to_zero=True, export_force_sampling=True,
        export_yup=True, export_extras=True, export_tangents=True,
        export_cameras=False, export_lights=False, export_materials="EXPORT",
    )
    mesh.data.calc_loop_triangles()
    lo, hi = kj.mesh_bounds(mesh)
    manifest = {
        "schema": SCHEMA,
        "asset_id": "kettlejack",
        "name": "Kettlejack",
        "coordinate_system": {"blender": "Z-up/-Y-forward", "gltf": "Y-up/+Z-forward", "units": "metres"},
        "donor": kj.DONOR,
        "source": {
            "kind": "authored interpretation of generated Kettlejack concept",
            "image_projection": False,
            "hidden_surfaces_inferred": True,
        },
        "recovery": {
            "from": "axm.game-assets.kettlejack-blender-foundry/v0.1",
            "failure": "pinned bpy 4.3 rejected export_merge_animation operator keyword",
            "repair": "remove unsupported exporter keyword; retain ACTIONS export and independent roundtrip verification",
            "failed_v0_1_retained": True,
        },
        "bounds_blender_m": {"min": lo, "max": hi, "height": hi[2]-lo[2]},
        "bones": [{"name": name, "parent": parent} for name, (_h, _t, parent) in kj.hero.bones.items()],
        "clips": [
            {"name": "Idle", "frames": [1, 61], "loop": True, "duration_s": 60/kj.FPS},
            {"name": "Run", "frames": [1, 25], "loop": True, "duration_s": 24/kj.FPS},
            {"name": "Jump", "frames": [1, 33], "loop": False, "duration_s": 32/kj.FPS},
            {"name": "Wrench_Swing", "frames": [1, 34], "loop": False, "duration_s": 33/kj.FPS},
            {"name": "Victory", "frames": [1, 41], "loop": False, "duration_s": 40/kj.FPS},
        ],
        "exports": {
            "glb": {"path": glb.name, "bytes": glb.stat().st_size, "sha256": kj.sha(glb)},
            "blend": {"path": blend.name, "bytes": blend.stat().st_size, "sha256": kj.sha(blend)},
        },
        "material_names": sorted({slot.material.name for slot in mesh.material_slots if slot.material}),
        "triangle_count": len(mesh.data.loop_triangles),
        "truth": {
            "real_geometry": True,
            "real_armature": True,
            "real_skin_weights": True,
            "real_animation_actions": True,
            "reference_pixel_faithful": False,
            "visual_acceptance": "REQUIRED",
            "game_engine_integration": "REQUIRED",
            "automatic_genome_mutation": False,
            "automatic_canon": False,
        },
    }
    kj.save_json(output / "character-manifest.json", manifest)
    return manifest


def main():
    kj.SCHEMA = SCHEMA
    kj.export = export_compat
    kj.main()


if __name__ == "__main__":
    main()
