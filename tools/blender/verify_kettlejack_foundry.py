"""Fresh-import verification for Game Asset Forge's Blender Kettlejack output.

This does not call the generating pose code. It verifies the exported GLB as a
consumer would see it: geometry, armature, weights, clip presence, sampled
finite deformation and grounded metre-scale bounds.
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


def bounds(objects):
    points = []
    for obj in objects:
        if obj.type != "MESH":
            continue
        points += [obj.matrix_world @ Vector(c) for c in obj.bound_box]
    if not points:
        raise ValueError("no imported mesh bounds")
    lo = [min(p[i] for p in points) for i in range(3)]
    hi = [max(p[i] for p in points) for i in range(3)]
    return lo, hi


def match_action(name):
    candidates = [a for a in bpy.data.actions if a.name == name or a.name.endswith(name) or name in a.name]
    return candidates[0] if candidates else None


def main():
    directory = Path(args().directory).resolve()
    manifest = json.loads((directory / "character-manifest.json").read_text())
    glb = directory / manifest["exports"]["glb"]["path"]
    clear()
    bpy.ops.import_scene.gltf(filepath=str(glb))
    arms = [o for o in bpy.context.scene.objects if o.type == "ARMATURE"]
    meshes = [o for o in bpy.context.scene.objects if o.type == "MESH"]
    failures = []
    if len(arms) != 1:
        failures.append(f"expected one armature, found {len(arms)}")
    if not meshes:
        failures.append("no mesh imported")
    arm = arms[0] if arms else None
    bone_names = sorted(b.name for b in arm.data.bones) if arm else []
    expected_bones = sorted(row["name"] for row in manifest["bones"])
    if bone_names != expected_bones:
        failures.append("imported bone names differ from manifest")
    if len(bone_names) < 20:
        failures.append("character skeleton unexpectedly small")

    weight_rows = 0
    bad_weights = 0
    for mesh in meshes:
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

    lo, hi = bounds(meshes)
    height = hi[2] - lo[2]
    if not .95 <= height <= 1.65:
        failures.append(f"unexpected imported character height {height}")
    if lo[2] < -.04 or lo[2] > .08:
        failures.append(f"rest pose not close to ground: min z {lo[2]}")

    actions = {}
    sampled = []
    if arm:
        arm.animation_data_create()
        for name in EXPECTED:
            action = match_action(name)
            actions[name] = action.name if action else None
            if action is None:
                failures.append(f"missing imported clip {name}")
                continue
            arm.animation_data.action = action
            start, end = action.frame_range
            for frame in (start, (start + end) * .5, end):
                bpy.context.scene.frame_set(int(round(frame)))
                bpy.context.view_layer.update()
                finite = True
                maximum = 0.0
                for mesh in meshes:
                    evaluated = mesh.evaluated_get(bpy.context.evaluated_depsgraph_get())
                    temporary = evaluated.to_mesh()
                    try:
                        for vertex in temporary.vertices:
                            co = evaluated.matrix_world @ vertex.co
                            finite = finite and all(math.isfinite(v) for v in co)
                            maximum = max(maximum, co.length)
                    finally:
                        evaluated.to_mesh_clear()
                sampled.append({"clip": name, "frame": float(frame), "finite": finite, "maximum_radius_m": maximum})
                if not finite or maximum > 5.0:
                    failures.append(f"invalid sampled deformation {name}@{frame}")

    report = {
        "schema": "axm.game-assets.kettlejack-foundry-roundtrip/v0.1",
        "status": "PASS" if not failures else "FAIL",
        "failures": failures,
        "glb": glb.name,
        "mesh_objects": len(meshes),
        "bone_count": len(bone_names),
        "bone_names": bone_names,
        "actions": actions,
        "weighted_vertices": weight_rows,
        "bad_weight_rows": bad_weights,
        "bounds_m": {"min": lo, "max": hi, "height": height},
        "sampled_deformation": sampled,
        "truth": "Fresh Blender import proves structural playback facts only; visual fidelity, gameplay controller behavior, engine performance and CANON remain separate gates.",
    }
    (directory / "roundtrip-verification.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, sort_keys=True))
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
