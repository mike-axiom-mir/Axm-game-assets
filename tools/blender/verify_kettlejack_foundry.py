"""Fresh-import verification for Game Asset Forge's Blender Kettlejack output.

This does not call the generating pose code. It verifies the exported GLB as a
consumer would see it: geometry, armature, weights, clip presence, sampled
finite deformation and grounded metre-scale bounds.

Blender's glTF importer may create a mesh object such as an Icosphere solely as
a pose-bone custom shape. That viewport helper is not exported character
geometry. It is excluded only when an imported pose bone actually references it,
matching the independently exercised Universal Creation verifier mechanism.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import sys

import bpy
from mathutils import Vector

EXPECTED = ["Idle", "Run", "Jump", "Wrench_Swing", "Victory"]


def args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
    p = argparse.ArgumentParser()
    p.add_argument("--directory", required=True)
    return p.parse_args(argv)


def clear():
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)


def character_meshes(arms):
    custom_shapes = {
        bone.custom_shape
        for arm in arms
        for bone in arm.pose.bones
        if bone.custom_shape is not None
    }
    meshes = [
        obj for obj in bpy.context.scene.objects
        if obj.type == "MESH" and obj not in custom_shapes
    ]
    return meshes, sorted(obj.name for obj in custom_shapes if obj is not None)


def positions(mesh):
    evaluated = mesh.evaluated_get(bpy.context.evaluated_depsgraph_get())
    temporary = evaluated.to_mesh()
    try:
        points = [tuple(evaluated.matrix_world @ vertex.co) for vertex in temporary.vertices]
    finally:
        evaluated.to_mesh_clear()
    if not points or not all(math.isfinite(value) for point in points for value in point):
        raise ValueError("empty or non-finite evaluated character mesh")
    return points


def bounds(objects):
    points = []
    for obj in objects:
        if obj.type != "MESH":
            continue
        points += [obj.matrix_world @ Vector(c) for c in obj.bound_box]
    if not points:
        raise ValueError("no imported character mesh bounds")
    lo = [min(p[i] for p in points) for i in range(3)]
    hi = [max(p[i] for p in points) for i in range(3)]
    return lo, hi


def match_action(name):
    candidates = [a for a in bpy.data.actions if a.name == name or a.name.endswith(name) or name in a.name]
    return candidates[0] if candidates else None


def reset_armature(arm):
    arm.animation_data_create()
    arm.animation_data.action = None
    for bone in arm.pose.bones:
        bone.location = (0, 0, 0)
        bone.rotation_mode = "XYZ"
        bone.rotation_euler = (0, 0, 0)
        bone.scale = (1, 1, 1)
    bpy.context.scene.frame_set(0)
    bpy.context.view_layer.update()


def main():
    directory = Path(args().directory).resolve()
    manifest = json.loads((directory / "character-manifest.json").read_text())
    glb = directory / manifest["exports"]["glb"]["path"]
    clear()
    bpy.ops.import_scene.gltf(filepath=str(glb))
    arms = [o for o in bpy.context.scene.objects if o.type == "ARMATURE"]
    meshes, helper_names = character_meshes(arms)
    failures = []
    if len(arms) != 1:
        failures.append(f"expected one armature, found {len(arms)}")
    if len(meshes) != 1:
        failures.append(f"expected one character mesh after helper exclusion, found {len(meshes)}")
    arm = arms[0] if arms else None
    bone_names = sorted(b.name for b in arm.data.bones) if arm else []
    expected_bones = sorted(row["name"] for row in manifest["bones"])
    if bone_names != expected_bones:
        failures.append("imported bone names differ from manifest")
    if len(bone_names) < 20:
        failures.append("character skeleton unexpectedly small")

    weight_rows = 0
    bad_weights = 0
    missing_groups = []
    for mesh in meshes:
        if arm:
            missing_groups += [group.name for group in mesh.vertex_groups if group.name not in arm.data.bones]
        for vertex in mesh.data.vertices:
            total = sum(group.weight for group in vertex.groups)
            if vertex.groups:
                weight_rows += 1
                if abs(total - 1.0) > 1e-4:
                    bad_weights += 1
    if weight_rows <= 0:
        failures.append("no imported skin weights")
    if bad_weights:
        failures.append(f"{bad_weights} imported vertices have non-normalized weights")
    if missing_groups:
        failures.append(f"vertex groups missing from armature: {sorted(set(missing_groups))}")

    if arm:
        reset_armature(arm)
    lo, hi = bounds(meshes)
    height = hi[2] - lo[2]
    if not .95 <= height <= 1.65:
        failures.append(f"unexpected imported character height {height}")
    if lo[2] < -.04 or lo[2] > .08:
        failures.append(f"rest pose not close to ground: min z {lo[2]}")

    actions = {}
    sampled = []
    if arm:
        for name in EXPECTED:
            action = match_action(name)
            actions[name] = action.name if action else None
            if action is None:
                failures.append(f"missing imported clip {name}")
                continue
            reset_armature(arm)
            arm.animation_data.action = action
            if getattr(action, "slots", None):
                try:
                    arm.animation_data.action_slot = action.slots[0]
                except Exception:
                    pass
            start, end = action.frame_range
            clip_motion = 0.0
            rest = positions(meshes[0]) if meshes else []
            for frame in (start, (start + end) * .5, end):
                bpy.context.scene.frame_set(int(frame), subframe=float(frame) - int(frame))
                bpy.context.view_layer.update()
                finite = True
                maximum = 0.0
                largest_motion = 0.0
                for mesh in meshes:
                    points = positions(mesh)
                    for index, co in enumerate(points):
                        finite = finite and all(math.isfinite(v) for v in co)
                        maximum = max(maximum, math.sqrt(sum(v*v for v in co)))
                        if mesh is meshes[0] and index < len(rest):
                            largest_motion = max(largest_motion, math.dist(rest[index], co))
                clip_motion = max(clip_motion, largest_motion)
                sampled.append({
                    "clip": name,
                    "frame": float(frame),
                    "finite": finite,
                    "maximum_radius_m": maximum,
                    "largest_motion_from_rest_m": largest_motion,
                })
                if not finite or maximum > 5.0:
                    failures.append(f"invalid sampled deformation {name}@{frame}")
            if clip_motion <= 1e-4:
                failures.append(f"clip does not visibly deform imported mesh: {name}")

    report = {
        "schema": "axm.game-assets.kettlejack-foundry-roundtrip/v0.2",
        "status": "PASS" if not failures else "FAIL",
        "failures": failures,
        "glb": glb.name,
        "character_mesh_objects": len(meshes),
        "excluded_importer_custom_shapes": helper_names,
        "bone_count": len(bone_names),
        "bone_names": bone_names,
        "actions": actions,
        "weighted_vertices": weight_rows,
        "bad_weight_rows": bad_weights,
        "missing_bone_groups": sorted(set(missing_groups)),
        "bounds_m": {"min": lo, "max": hi, "height": height},
        "sampled_deformation": sampled,
        "truth": "Fresh Blender import proves structural playback facts. Importer-created pose-bone custom-shape meshes are excluded only by actual helper references. Visual fidelity, gameplay controller behavior, engine performance and CANON remain separate gates.",
    }
    (directory / "roundtrip-verification.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, sort_keys=True))
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
