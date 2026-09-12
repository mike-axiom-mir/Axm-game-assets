"""Render retained visual evidence from a fresh Kettlejack GLB import.

The glTF importer can create a mesh used only as a pose-bone custom shape. It
must not participate in character framing. We exclude only mesh objects that an
imported pose bone actually references as ``custom_shape``.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import sys

import bpy
from mathutils import Vector


def args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
    p = argparse.ArgumentParser()
    p.add_argument("--directory", required=True)
    p.add_argument("--resolution", type=int, default=640)
    return p.parse_args(argv)


def clear():
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)


def action(name):
    rows = [a for a in bpy.data.actions if a.name == name or a.name.endswith(name) or name in a.name]
    if not rows:
        raise ValueError(f"missing imported action {name}")
    return rows[0]


def character_meshes(arms):
    custom_shapes = {
        bone.custom_shape
        for arm in arms
        for bone in arm.pose.bones
        if bone.custom_shape is not None
    }
    return [obj for obj in bpy.context.scene.objects if obj.type == "MESH" and obj not in custom_shapes]


def set_action(arm, act):
    arm.animation_data_create()
    arm.animation_data.action = act
    if getattr(act, "slots", None):
        try:
            arm.animation_data.action_slot = act.slots[0]
        except Exception:
            pass


def world_bounds(objects):
    points=[]
    for obj in objects:
        if obj.type == "MESH":
            points += [obj.matrix_world @ Vector(c) for c in obj.bound_box]
    if not points:
        raise ValueError("no character mesh bounds")
    lo=Vector(tuple(min(p[i] for p in points) for i in range(3)))
    hi=Vector(tuple(max(p[i] for p in points) for i in range(3)))
    return lo,hi


def studio(resolution):
    scene=bpy.context.scene
    scene.render.engine="BLENDER_EEVEE_NEXT"
    scene.render.resolution_x=resolution
    scene.render.resolution_y=resolution
    scene.render.resolution_percentage=100
    scene.render.image_settings.file_format="PNG"
    scene.render.film_transparent=False
    scene.render.fps=30
    scene.world.color=(.035,.040,.052)
    world=scene.world
    world.use_nodes=True
    bg=world.node_tree.nodes.get("Background")
    bg.inputs["Color"].default_value=(.026,.032,.044,1)
    bg.inputs["Strength"].default_value=.45

    bpy.ops.object.light_add(type="AREA", location=(-2.0,-2.6,3.2))
    key=bpy.context.object;key.name="Key";key.data.energy=850;key.data.shape="DISK";key.data.size=2.2
    key.rotation_euler=(math.radians(25),0,math.radians(-35))
    bpy.ops.object.light_add(type="AREA", location=(2.3,-1.4,2.1))
    fill=bpy.context.object;fill.name="Fill";fill.data.energy=500;fill.data.size=2.0
    bpy.ops.object.light_add(type="AREA", location=(1.0,2.0,2.6))
    rim=bpy.context.object;rim.name="Rim";rim.data.energy=700;rim.data.size=1.7

    bpy.ops.mesh.primitive_plane_add(size=6, location=(0,0,-.006))
    floor=bpy.context.object;floor.name="ReviewFloor"
    mat=bpy.data.materials.new("ReviewFloorMat");mat.diffuse_color=(.12,.13,.15,1);mat.use_nodes=True
    bsdf=mat.node_tree.nodes.get("Principled BSDF");bsdf.inputs["Base Color"].default_value=(.12,.13,.15,1);bsdf.inputs["Roughness"].default_value=.88
    floor.data.materials.append(mat)

    bpy.ops.object.camera_add()
    cam=bpy.context.object;cam.name="ReviewCamera";cam.data.lens=58
    scene.camera=cam
    return cam


def point_camera(cam, location, target):
    cam.location=location
    cam.rotation_euler=(Vector(target)-Vector(location)).to_track_quat("-Z","Y").to_euler()


def render(path, cam, location, target):
    point_camera(cam, location, target)
    scene=bpy.context.scene
    scene.render.filepath=str(path)
    bpy.ops.render.render(write_still=True)
    if not path.is_file() or path.stat().st_size < 3000:
        raise ValueError(f"render failed or empty: {path}")


def main():
    a=args();directory=Path(a.directory).resolve();resolution=max(320,min(1200,a.resolution))
    manifest=json.loads((directory/"character-manifest.json").read_text())
    clear();bpy.ops.import_scene.gltf(filepath=str(directory/manifest["exports"]["glb"]["path"]))
    armatures=[o for o in bpy.context.scene.objects if o.type=="ARMATURE"]
    meshes=character_meshes(armatures)
    if len(armatures)!=1 or len(meshes)!=1:
        raise ValueError(f"fresh render import expected one rig/character mesh, got {len(armatures)}/{len(meshes)}")
    arm=armatures[0];arm.animation_data_create();cam=studio(resolution)
    lo,hi=world_bounds(meshes);center=(lo+hi)*.5;height=hi.z-lo.z
    target=(center.x,center.y,lo.z+height*.53)
    distance=max(2.35,height*2.15)

    views=[]
    static=[
        ("front",(0,-distance,lo.z+height*.58)),
        ("three_quarter",(distance*.66,-distance*.82,lo.z+height*.62)),
        ("side",(distance,0,lo.z+height*.58)),
        ("back",(0,distance,lo.z+height*.58)),
    ]
    idle=action("Idle");set_action(arm,idle);bpy.context.scene.frame_set(int(idle.frame_range[0]));bpy.context.view_layer.update()
    proof=directory/"proof";proof.mkdir(exist_ok=True)
    for name,location in static:
        path=proof/f"{name}.png";render(path,cam,location,target);views.append({"name":name,"clip":"Idle","frame":float(idle.frame_range[0]),"path":str(path.relative_to(directory))})

    motion=[("idle","Idle",.50),("run","Run",.25),("jump","Jump",.50),("wrench_swing","Wrench_Swing",.55),("victory","Victory",.50)]
    for view_name,clip_name,fraction in motion:
        act=action(clip_name);set_action(arm,act)
        start,end=act.frame_range;frame=int(round(start+(end-start)*fraction));bpy.context.scene.frame_set(frame);bpy.context.view_layer.update()
        # Motion can change bounds substantially (especially jump and staff swing),
        # so reframe from the actual sampled pose rather than bind-pose bounds.
        pose_lo,pose_hi=world_bounds(meshes)
        pose_center=(pose_lo+pose_hi)*.5;pose_height=pose_hi.z-pose_lo.z
        pose_target=(pose_center.x,pose_center.y,pose_lo.z+pose_height*.53)
        pose_distance=max(2.35,pose_height*2.15)
        path=proof/f"{view_name}.png"
        render(path,cam,(pose_distance*.62,-pose_distance*.86,pose_lo.z+pose_height*.62),pose_target)
        views.append({"name":view_name,"clip":clip_name,"frame":frame,"path":str(path.relative_to(directory))})

    receipt={
        "schema":"axm.game-assets.kettlejack-foundry-render/v0.2","status":"PASS","fresh_import":True,
        "renderer":"Blender EEVEE Next via bpy 4.3","resolution":[resolution,resolution],"views":views,
        "truth":"These are retained pixels rendered from a freshly imported exported GLB. Importer-only custom-shape helpers are excluded from framing by actual pose-bone references. They are visual evidence for review, not automatic aesthetic acceptance or game-engine certification."
    }
    (directory/"render-receipt.json").write_text(json.dumps(receipt,indent=2,sort_keys=True)+"\n")
    print(json.dumps(receipt,sort_keys=True))


if __name__=="__main__":main()
