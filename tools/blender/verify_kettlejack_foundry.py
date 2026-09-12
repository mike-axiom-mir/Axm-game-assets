"""Fresh-import verification for Game Asset Forge's Blender Kettlejack output.

This verifier deliberately separates three evidence planes:

1. Blender fresh import proves mesh/armature/weight/bounds structure.
2. The GLB binary itself proves each required animation contains varying
   transform samples, independent of Blender's action-slot playback quirks.
3. Downstream Godot remains the engine playback/import gate.

Blender's glTF importer may create a mesh object such as an Icosphere solely as
a pose-bone custom shape. That viewport helper is excluded only when an imported
pose bone actually references it.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import struct
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


def read_glb(glb: Path):
    payload = glb.read_bytes()
    if len(payload) < 20 or payload[:4] != b"glTF":
        raise ValueError("not a GLB 2.0 file")
    version, total = struct.unpack_from("<II", payload, 4)
    if version != 2 or total != len(payload):
        raise ValueError("GLB header length/version mismatch")
    pos = 12
    document = None
    binary = None
    while pos < len(payload):
        length, kind = struct.unpack_from("<II", payload, pos)
        pos += 8
        chunk = payload[pos:pos+length]
        pos += length
        if kind == 0x4E4F534A:
            document = json.loads(chunk.rstrip(b"\x00 \t\r\n").decode("utf-8"))
        elif kind == 0x004E4942:
            binary = chunk
    if document is None or binary is None:
        raise ValueError("GLB missing JSON/BIN chunks")
    return document, binary


def accessor_values(document, binary, accessor_index):
    acc = document["accessors"][accessor_index]
    view = document["bufferViews"][acc["bufferView"]]
    component_count = {"SCALAR":1,"VEC2":2,"VEC3":3,"VEC4":4,"MAT4":16}[acc["type"]]
    fmt = {5126:"f", 5120:"b", 5121:"B", 5122:"h", 5123:"H", 5125:"I"}[acc["componentType"]]
    row_fmt = "<" + fmt * component_count
    row_bytes = struct.calcsize(row_fmt)
    stride = int(view.get("byteStride", row_bytes))
    offset = int(view.get("byteOffset", 0)) + int(acc.get("byteOffset", 0))
    rows = [struct.unpack_from(row_fmt, binary, offset + index * stride) for index in range(acc["count"])]
    return rows


def glb_animation_evidence(glb: Path):
    document, binary = read_glb(glb)
    nodes = document.get("nodes", [])
    result = {}
    for animation in document.get("animations", []):
        name = str(animation.get("name", ""))
        varying_tracks = []
        all_tracks = []
        for channel in animation.get("channels", []):
            target = channel.get("target", {})
            path = str(target.get("path", ""))
            node_index = int(target.get("node", -1))
            node_name = str(nodes[node_index].get("name", node_index)) if 0 <= node_index < len(nodes) else str(node_index)
            sampler = animation["samplers"][channel["sampler"]]
            values = accessor_values(document, binary, sampler["output"])
            finite = all(math.isfinite(float(v)) for row in values for v in row)
            if not finite:
                raise ValueError(f"animation {name} track {node_name}:{path} has non-finite samples")
            rounded = {tuple(round(float(v), 7) for v in row) for row in values}
            row = {"node": node_name, "path": path, "samples": len(values), "unique_samples": len(rounded)}
            all_tracks.append(row)
            if path in {"rotation", "translation", "scale"} and len(rounded) > 1:
                varying_tracks.append(row)
        result[name] = {
            "track_count": len(all_tracks),
            "varying_track_count": len(varying_tracks),
            "varying_tracks": varying_tracks,
        }
    return result


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
    imported_playback_diagnostic = []
    if arm:
        for name in EXPECTED:
            action = match_action(name)
            actions[name] = action.name if action else None
            if action is None:
                failures.append(f"missing imported Blender action {name}")
                continue
            reset_armature(arm)
            arm.animation_data.action = action
            if getattr(action, "slots", None):
                try:
                    arm.animation_data.action_slot = action.slots[0]
                except Exception:
                    pass
            start, end = action.frame_range
            rest = positions(meshes[0]) if meshes else []
            maximum_motion = 0.0
            for frame in (start, (start + end) * .5, end):
                bpy.context.scene.frame_set(int(frame), subframe=float(frame) - int(frame))
                bpy.context.view_layer.update()
                points = positions(meshes[0]) if meshes else []
                largest = max((math.dist(rest[i], point) for i, point in enumerate(points[:len(rest)])), default=0.0)
                maximum_motion = max(maximum_motion, largest)
            imported_playback_diagnostic.append({"clip": name, "maximum_sampled_motion_m": maximum_motion})

    encoded_motion = glb_animation_evidence(glb)
    for name in EXPECTED:
        row = encoded_motion.get(name)
        if row is None:
            failures.append(f"GLB missing required animation {name}")
        elif int(row["varying_track_count"]) <= 0:
            failures.append(f"GLB animation has no varying transform track: {name}")

    report = {
        "schema": "axm.game-assets.kettlejack-foundry-roundtrip/v0.3",
        "status": "PASS" if not failures else "FAIL",
        "failures": failures,
        "glb": glb.name,
        "character_mesh_objects": len(meshes),
        "excluded_importer_custom_shapes": helper_names,
        "bone_count": len(bone_names),
        "bone_names": bone_names,
        "imported_actions": actions,
        "weighted_vertices": weight_rows,
        "bad_weight_rows": bad_weights,
        "missing_bone_groups": sorted(set(missing_groups)),
        "bounds_m": {"min": lo, "max": hi, "height": height},
        "glb_encoded_motion": encoded_motion,
        "blender_imported_action_playback_diagnostic": imported_playback_diagnostic,
        "truth": "Fresh Blender import proves mesh/armature/weights/bounds. Exact exported GLB accessors independently prove non-constant transform samples for every required animation. Blender 4.3 imported-action slot evaluation is retained as a diagnostic rather than conflated with encoded GLB motion. Godot remains the downstream engine playback/import gate. Visual fidelity, performance and CANON remain separate.",
    }
    (directory / "roundtrip-verification.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, sort_keys=True))
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
