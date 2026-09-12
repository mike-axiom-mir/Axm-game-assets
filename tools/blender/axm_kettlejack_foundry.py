"""AXM Game Asset Forge — Kettlejack Blender character foundry v0.1.

This is the first deliberate architectural jump away from repeatedly dressing an
adult HM08 substrate after retained renders proved that topology-preserving
patches were not converging on the stylized reference.

The authoring language selectively adapts mechanisms proven by Universal
Creation's rigged-character work at commit
78b16c01b543733688d7d036552b63679c87c10b, especially:

- tools/blender/axm_chaos_hero.py: authored reference-guided anatomy/details;
- tools/blender/axm_hero_motion.py: rigid shell skinning and ordinary skeletal clips;
- tools/blender/axm_oops_character.py: retained editable pieces and portable GLB export.

The Kettlejack concept is art-direction input. Geometry below is an authored
interpretation, not automatic image-to-3D reconstruction. Hidden surfaces are
inferred. The source image is never projected onto the mesh.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import sys

import bpy
from mathutils import Vector

DONOR = {
    "repo": "mike-axiom-mir/axm-universal-creation",
    "commit": "78b16c01b543733688d7d036552b63679c87c10b",
    "mechanisms": [
        "tools/blender/axm_chaos_hero.py",
        "tools/blender/axm_hero_motion.py",
        "tools/blender/axm_oops_character.py",
    ],
}
SCHEMA = "axm.game-assets.kettlejack-blender-foundry/v0.1"
ASSET_NAME = "AXM_Kettlejack"
FPS = 30
EXPECTED_CLIPS = ["Idle", "Run", "Jump", "Wrench_Swing", "Victory"]


def parse_args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
    p = argparse.ArgumentParser()
    p.add_argument("--output", required=True)
    return p.parse_args(argv)


def sha(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def save_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")


def clear_scene() -> None:
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    for collection in list(bpy.data.collections):
        if collection.name != "Collection" and collection.users == 0:
            bpy.data.collections.remove(collection)


def srgb(hex_value: str):
    value = hex_value.lstrip("#")
    rgb = tuple(int(value[i:i+2], 16) / 255.0 for i in (0, 2, 4))
    return (*rgb, 1.0)


def material(name: str, color: str, *, metallic=0.0, roughness=.55, emission=None, emission_strength=0.0):
    mat = bpy.data.materials.new(name)
    mat.diffuse_color = srgb(color)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = srgb(color)
    bsdf.inputs["Metallic"].default_value = float(metallic)
    bsdf.inputs["Roughness"].default_value = float(roughness)
    if emission:
        socket = bsdf.inputs.get("Emission Color") or bsdf.inputs.get("Emission")
        if socket:
            socket.default_value = srgb(emission)
        strength = bsdf.inputs.get("Emission Strength")
        if strength:
            strength.default_value = float(emission_strength)
    return mat


def apply_modifiers(obj):
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    for modifier in list(obj.modifiers):
        try:
            bpy.ops.object.modifier_apply(modifier=modifier.name)
        except RuntimeError:
            pass
    obj.select_set(False)
    return obj


def assign(obj, mat):
    if obj.data and hasattr(obj.data, "materials"):
        obj.data.materials.append(mat)
    return obj


def sphere(name, location, dims, mat, *, segments=32, rings=20):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=segments, ring_count=rings, location=location)
    obj = bpy.context.object
    obj.name = name
    obj.scale = dims
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    assign(obj, mat)
    for poly in obj.data.polygons:
        poly.use_smooth = True
    return obj


def box(name, location, dims, mat, *, bevel=.012, rotation=(0, 0, 0)):
    bpy.ops.mesh.primitive_cube_add(size=1, location=location, rotation=rotation)
    obj = bpy.context.object
    obj.name = name
    obj.dimensions = dims
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    assign(obj, mat)
    if bevel > 0:
        mod = obj.modifiers.new("soft manufactured edges", "BEVEL")
        mod.width = min(float(bevel), min(dims) * .24)
        mod.segments = 3
        apply_modifiers(obj)
    return obj


def cylinder(name, location, radius, depth, mat, *, axis=(0, 0, 1), vertices=24, bevel=.004):
    bpy.ops.mesh.primitive_cylinder_add(vertices=vertices, radius=radius, depth=depth, location=location)
    obj = bpy.context.object
    obj.name = name
    direction = Vector(axis)
    if direction.length <= 1e-8:
        raise ValueError("cylinder axis must be non-zero")
    obj.rotation_mode = "QUATERNION"
    obj.rotation_quaternion = direction.normalized().to_track_quat("Z", "Y")
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    assign(obj, mat)
    if bevel:
        mod = obj.modifiers.new("edge rolloff", "BEVEL")
        mod.width = min(bevel, radius * .25, depth * .08)
        mod.segments = 2
        apply_modifiers(obj)
    for poly in obj.data.polygons:
        poly.use_smooth = True
    return obj


def torus(name, location, major, minor, mat, *, scale_xyz=(1, 1, 1), rotation=(0, 0, 0), major_segments=28, minor_segments=8):
    bpy.ops.mesh.primitive_torus_add(major_radius=major, minor_radius=minor, major_segments=major_segments,
                                    minor_segments=minor_segments, location=location, rotation=rotation)
    obj = bpy.context.object
    obj.name = name
    obj.scale = scale_xyz
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    assign(obj, mat)
    for poly in obj.data.polygons:
        poly.use_smooth = True
    return obj


def beam(name, a, b, radius, mat, *, vertices=16):
    a, b = Vector(a), Vector(b)
    return cylinder(name, tuple((a + b) * .5), radius, (b - a).length, mat,
                    axis=tuple(b - a), vertices=vertices, bevel=min(.004, radius * .18))


class Kettlejack:
    def __init__(self, output: Path):
        self.output = output
        self.parts: list[bpy.types.Object] = []
        self.bones = {}
        self.mat = {
            "skin": material("KJ_Skin", "#e6a48b", roughness=.58),
            "cheek": material("KJ_Cheek", "#ef8d79", roughness=.60),
            "hair": material("KJ_Hair", "#3b281f", roughness=.78),
            "white": material("KJ_White", "#eee5d4", roughness=.38),
            "eye": material("KJ_Eye", "#32241d", roughness=.20),
            "pants": material("KJ_Pants", "#4e5747", roughness=.82),
            "shirt": material("KJ_Shirt", "#c5b79a", roughness=.78),
            "scarf": material("KJ_Scarf", "#b64d2c", roughness=.75),
            "leather": material("KJ_Leather", "#684735", roughness=.72),
            "dark_leather": material("KJ_DarkLeather", "#3d3028", roughness=.76),
            "steel": material("KJ_Steel", "#7d8586", metallic=.85, roughness=.36),
            "iron": material("KJ_Iron", "#343a3d", metallic=.72, roughness=.54),
            "ivory": material("KJ_IvoryEnamel", "#d8d0bd", metallic=.35, roughness=.44),
            "rust": material("KJ_RustRed", "#9e392c", metallic=.48, roughness=.56),
            "yellow": material("KJ_SafetyYellow", "#d79b27", metallic=.38, roughness=.48),
            "teal": material("KJ_TealWrap", "#3e7680", roughness=.72),
            "rubber": material("KJ_Rubber", "#25292a", roughness=.86),
            "brass": material("KJ_Brass", "#b5833e", metallic=.72, roughness=.38),
            "glow": material("KJ_Glow", "#ef6d1e", metallic=.10, roughness=.30, emission="#ff7d20", emission_strength=4.0),
        }

    def add(self, obj, bone):
        obj["axm_bone"] = bone
        self.parts.append(obj)
        return obj

    def ball(self, name, c, d, m, bone, **kw):
        return self.add(sphere(name, c, d, self.mat[m], **kw), bone)

    def box(self, name, c, d, m, bone, **kw):
        return self.add(box(name, c, d, self.mat[m], **kw), bone)

    def cyl(self, name, c, r, depth, m, bone, **kw):
        return self.add(cylinder(name, c, r, depth, self.mat[m], **kw), bone)

    def torus(self, name, c, major, minor, m, bone, **kw):
        return self.add(torus(name, c, major, minor, self.mat[m], **kw), bone)

    def beam(self, name, a, b, r, m, bone, **kw):
        return self.add(beam(name, a, b, r, self.mat[m], **kw), bone)

    def bone(self, name, head, tail, parent=None):
        self.bones[name] = (tuple(head), tuple(tail), parent)

    def skeleton_contract(self):
        self.bone("Root", (0, 0, 0), (0, 0, .08))
        self.bone("Pelvis", (0, 0, .56), (0, 0, .69), "Root")
        self.bone("Chest", (0, 0, .69), (0, 0, .94), "Pelvis")
        self.bone("Head", (0, 0, .94), (0, 0, 1.22), "Chest")
        self.bone("Jaw", (0, -.05, 1.055), (0, -.07, .995), "Head")
        self.bone("ScarfTail", (.10, 0, .91), (.16, .03, .74), "Chest")
        self.bone("Pack", (0, .10, .78), (0, .17, .98), "Chest")
        for sign, side in ((-1, "R"), (1, "L")):
            self.bone(f"UpperArm.{side}", (sign*.19, 0, .88), (sign*.31, 0, .72), "Chest")
            self.bone(f"Forearm.{side}", (sign*.31, 0, .72), (sign*.37, -.015, .57), f"UpperArm.{side}")
            self.bone(f"Hand.{side}", (sign*.37, -.015, .57), (sign*.38, -.055, .49), f"Forearm.{side}")
            self.bone(f"Thigh.{side}", (sign*.10, 0, .57), (sign*.11, -.01, .34), "Pelvis")
            self.bone(f"Shin.{side}", (sign*.11, -.01, .34), (sign*.12, 0, .13), f"Thigh.{side}")
            self.bone(f"Foot.{side}", (sign*.12, 0, .13), (sign*.12, -.13, .08), f"Shin.{side}")
        self.bone("Tool", (-.38, -.05, .55), (-.38, -.05, .92), "Hand.R")

    def face_and_head(self):
        self.ball("Head soft base", (0, -.005, 1.075), (.198, .166, .214), "skin", "Head", segments=48, rings=32)
        for sign in (-1, 1):
            self.ball("Ear", (sign*.188, -.005, 1.075), (.048, .030, .062), "skin", "Head", segments=24, rings=16)
            self.ball("Warm cheek", (sign*.112, -.146, 1.035), (.063, .022, .050), "cheek", "Head", segments=24, rings=16)

        # Eyes are deliberately embedded near the face plane instead of floating discs.
        for sign in (-1, 1):
            x = sign*.070
            self.ball("Eye white", (x, -.160, 1.105), (.052, .018, .061), "white", "Head", segments=32, rings=20)
            self.ball("Brown iris", (x, -.177, 1.105), (.025, .007, .030), "eye", "Head", segments=24, rings=16)
            self.ball("Eye glint", (x-sign*.007, -.184, 1.121), (.006, .003, .007), "white", "Head", segments=12, rings=8)
            self.beam("Expressive brow",
                      (x-sign*.043, -.163, 1.170), (x+sign*.039, -.166, 1.177),
                      .007, "hair", "Head", vertices=12)

        self.ball("Peach nose", (0, -.176, 1.060), (.033, .024, .030), "cheek", "Head", segments=24, rings=16)
        # Concave-looking smile language: dark curved segments behind cream teeth.
        self.beam("Smile left", (-.070, -.168, 1.012), (0, -.181, .996), .009, "eye", "Head", vertices=12)
        self.beam("Smile right", (0, -.181, .996), (.070, -.168, 1.012), .009, "eye", "Head", vertices=12)
        for x, z in ((-.045, 1.009), (-.015, 1.002), (.015, 1.002), (.045, 1.009)):
            self.box("Smile tooth", (x, -.181, z), (.027, .012, .026), "white", "Head", bevel=.006)

        # Hair mass and swept clumps.
        self.ball("Hair cap", (0, .005, 1.230), (.202, .169, .112), "hair", "Head", segments=40, rings=24)
        for i, (x, y, z, sx, sy, sz) in enumerate((
            (-.13, -.10, 1.218, .075, .050, .055), (-.07, -.125, 1.248, .080, .045, .065),
            (.00, -.132, 1.255, .085, .043, .067), (.075, -.118, 1.247, .075, .047, .062),
            (.135, -.090, 1.220, .065, .052, .055), (-.17, -.030, 1.160, .052, .040, .075),
            (.17, -.025, 1.155, .050, .040, .070),
        )):
            self.ball(f"Hair clump {i}", (x, y, z), (sx, sy, sz), "hair", "Head", segments=20, rings=12)

        # Pilot cap and goggles stay visibly above the eyes.
        self.ball("Pilot cap", (0, .015, 1.260), (.176, .150, .067), "leather", "Head", segments=32, rings=18)
        for sign in (-1, 1):
            x = sign*.068
            self.torus("Raised goggle rim", (x, -.122, 1.266), .050, .010, "brass", "Head",
                       rotation=(math.pi/2, 0, 0), major_segments=28, minor_segments=8)
            self.cyl("Raised goggle lens", (x, -.130, 1.266), .040, .010, "iron", "Head",
                     axis=(0, -1, 0), vertices=28, bevel=.002)
        self.beam("Goggle bridge", (-.018, -.126, 1.266), (.018, -.126, 1.266), .006, "steel", "Head")
        self.torus("Goggle head strap", (0, .010, 1.226), .178, .010, "dark_leather", "Head",
                   scale_xyz=(1, .84, 1), major_segments=32, minor_segments=7)

    def torso_and_clothes(self):
        self.ball("Padded shirt torso", (0, 0, .795), (.175, .125, .195), "shirt", "Chest", segments=36, rings=24)
        self.ball("Baggy pants pelvis", (0, .005, .590), (.172, .125, .125), "pants", "Pelvis", segments=32, rings=20)
        # Layered vest plates, straps and patch history.
        self.box("Vest left", (-.064, -.116, .806), (.100, .032, .205), "shirt", "Chest", bevel=.016)
        self.box("Vest right", (.064, -.116, .806), (.100, .032, .205), "shirt", "Chest", bevel=.016)
        for sign in (-1, 1):
            self.beam("Harness strap", (sign*.085, -.135, .900), (sign*.105, -.142, .665), .013, "leather", "Chest", vertices=12)
        self.box("Chest repair plate", (-.071, -.140, .775), (.065, .014, .072), "ivory", "Chest", bevel=.006)

        # Scarf collar is layered and the tail is separately articulated.
        for z, scale_x in ((.927, 1.0), (.913, .94), (.900, .88)):
            self.torus("Folded orange scarf", (0, 0, z), .161*scale_x, .027, "scarf", "Chest",
                       scale_xyz=(1, .74, 1), major_segments=32, minor_segments=8)
        self.ball("Scarf knot", (.115, -.090, .900), (.045, .035, .038), "scarf", "Chest", segments=20, rings=12)
        self.beam("Scarf tail", (.118, -.060, .890), (.160, .015, .735), .035, "scarf", "ScarfTail", vertices=12)

        # Belt and pouch clutter establish scale and lived-in character.
        self.torus("Tool belt", (0, 0, .655), .170, .026, "leather", "Pelvis", scale_xyz=(1, .72, 1), major_segments=30, minor_segments=8)
        for i, x in enumerate((-.135, -.045, .050, .140)):
            self.box(f"Belt pouch {i}", (x, -.135, .620), (.072, .050, .078), "leather", "Pelvis", bevel=.012)
            self.box(f"Pouch flap {i}", (x, -.164, .643), (.066, .010, .030), "dark_leather", "Pelvis", bevel=.005)
        self.torus("Belt steel ring", (.135, -.165, .555), .030, .006, "steel", "Pelvis",
                   rotation=(math.pi/2, 0, 0), major_segments=18, minor_segments=6)

    def limbs(self):
        for sign, side in ((-1, "R"), (1, "L")):
            shoulder = (sign*.205, 0, .875)
            elbow = (sign*.310, -.005, .720)
            wrist = (sign*.365, -.020, .570)
            # Rolled sleeves and exposed forearms overlap joint seams.
            self.ball(f"{side} rolled sleeve", (sign*.245, -.005, .820), (.078, .073, .103), "shirt", f"UpperArm.{side}", segments=24, rings=16)
            self.beam(f"{side} forearm", elbow, wrist, .048, "skin", f"Forearm.{side}", vertices=18)
            self.torus(f"{side} sleeve cuff", tuple(Vector(elbow)*.98 + Vector(shoulder)*.02), .056, .012, "shirt", f"Forearm.{side}",
                       rotation=(0, math.pi/2, 0), major_segments=20, minor_segments=6)
            self.ball(f"{side} glove palm", (sign*.375, -.030, .535), (.062, .050, .055), "dark_leather", f"Hand.{side}", segments=20, rings=12)
            self.box(f"{side} glove plate", (sign*.375, -.074, .548), (.082, .018, .060), "iron", f"Hand.{side}", bevel=.010)
            for i in range(3):
                self.beam(f"{side} glove finger {i}", (sign*(.345+i*.025), -.068, .520), (sign*(.345+i*.025), -.090, .485), .012,
                          "dark_leather", f"Hand.{side}", vertices=10)

            hip = (sign*.100, 0, .570)
            knee = (sign*.110, -.005, .340)
            ankle = (sign*.120, 0, .130)
            self.ball(f"{side} cargo thigh", (sign*.105, -.004, .455), (.092, .080, .145), "pants", f"Thigh.{side}", segments=28, rings=18)
            self.torus(f"{side} rolled trouser cuff", (sign*.112, 0, .335), .080, .019, "shirt", f"Shin.{side}",
                       scale_xyz=(1, .86, 1), major_segments=24, minor_segments=7)
            if side == "L":
                # Heavy conventional work boot.
                self.ball("Left boot upper", (sign*.120, -.020, .205), (.086, .080, .105), "leather", "Shin.L", segments=24, rings=16)
                self.box("Left boot sole", (sign*.120, -.055, .070), (.205, .260, .125), "rubber", "Foot.L", bevel=.030)
                self.box("Left metal toe", (sign*.120, -.145, .095), (.190, .105, .095), "steel", "Foot.L", bevel=.030)
                for z in (.145, .180, .215):
                    self.beam("Left boot lace", (sign*.065, -.100, z), (sign*.175, -.100, z+.005), .006, "shirt", "Shin.L", vertices=10)
            else:
                # Exposed spring/piston prosthetic right lower leg.
                self.cyl("Mechanical shin piston", (sign*.115, -.005, .245), .035, .235, "steel", "Shin.R", vertices=20)
                self.box("Mechanical knee casing", (sign*.110, -.005, .345), (.120, .100, .105), "yellow", "Shin.R", bevel=.025)
                for z in (.175, .215, .255, .295):
                    self.torus("Mechanical leg spring", (sign*.115, -.005, z), .058, .008, "brass", "Shin.R",
                               scale_xyz=(1, .88, 1), major_segments=22, minor_segments=6)
                self.box("Mechanical foot", (sign*.120, -.060, .065), (.215, .270, .125), "yellow", "Foot.R", bevel=.030)
                self.box("Mechanical toe cap", (sign*.120, -.155, .090), (.198, .105, .090), "steel", "Foot.R", bevel=.028)

    def shoulder_and_pack(self):
        # Dented-looking hubcap: layered discs and fasteners, large enough to read at game distance.
        self.cyl("Hubcap shoulder iron backing", (.245, -.095, .875), .120, .038, "iron", "UpperArm.L", axis=(0, -1, 0), vertices=36)
        self.cyl("Hubcap shoulder enamel", (.245, -.118, .875), .112, .020, "ivory", "UpperArm.L", axis=(0, -1, 0), vertices=36)
        self.cyl("Hubcap center", (.245, -.132, .875), .031, .018, "steel", "UpperArm.L", axis=(0, -1, 0), vertices=24)
        for i in range(6):
            a = math.tau*i/6
            self.cyl("Hubcap bolt", (.245+math.cos(a)*.078, -.142, .875+math.sin(a)*.078), .007, .012, "steel", "UpperArm.L",
                     axis=(0, -1, 0), vertices=10, bevel=.001)

        # Kettle backpack on the back (+Y) with readable side vent/exhaust.
        self.ball("Kettle pack enamel body", (0, .155, .800), (.145, .130, .165), "ivory", "Pack", segments=32, rings=20)
        self.cyl("Kettle pack lid", (0, .155, .965), .092, .032, "steel", "Pack", vertices=28)
        self.ball("Kettle lid knob", (0, .155, 1.000), (.026, .026, .026), "leather", "Pack", segments=16, rings=10)
        for x in (-.135, .135):
            self.beam("Kettle pack frame", (x, .085, .640), (x, .110, .955), .016, "iron", "Pack", vertices=10)
        self.box("Kettle glowing vent", (.135, .100, .785), (.045, .035, .125), "glow", "Pack", bevel=.010)
        self.torus("Kettle pressure gauge", (-.105, .075, .895), .031, .007, "brass", "Pack",
                   rotation=(math.pi/2, 0, 0), major_segments=18, minor_segments=6)
        self.beam("Kettle gauge needle", (-.105, .068, .895), (-.093, .066, .906), .0025, "iron", "Pack", vertices=8)
        self.beam("Kettle spout lower", (.105, .160, .900), (.180, .160, .955), .027, "steel", "Pack", vertices=16)
        self.beam("Kettle spout upper", (.180, .160, .955), (.205, .155, 1.030), .023, "steel", "Pack", vertices=16)
        self.cyl("Kettle exhaust lip", (.207, .155, 1.040), .034, .024, "iron", "Pack", axis=(.2, 0, 1), vertices=20)
        self.torus("Kettle carry handle", (0, .165, 1.000), .125, .012, "leather", "Pack",
                   rotation=(math.pi/2, 0, 0), scale_xyz=(1, 1, .55), major_segments=28, minor_segments=7)

    def wrench(self):
        # Tool lives to the character's right (-X) so front review never hides the face.
        x, y = -.405, -.055
        self.cyl("Wrench staff shaft", (x, y, .635), .026, 1.08, "rust", "Tool", vertices=18)
        for z in (.245, .305, .365):
            self.torus("Wrench cloth wrap", (x, y, z), .031, .006, "teal", "Tool", major_segments=18, minor_segments=6)
        self.box("Wrench jaw body", (x-.010, y, 1.175), (.235, .060, .074), "steel", "Tool", bevel=.018)
        # Clear adjustable/open jaw silhouette with unequal jaws.
        self.beam("Wrench fixed jaw", (x-.115, y, 1.190), (x-.165, y, 1.310), .034, "rust", "Tool", vertices=14)
        self.beam("Wrench moving jaw", (x+.060, y, 1.190), (x+.103, y, 1.280), .030, "rust", "Tool", vertices=14)
        self.box("Wrench fixed jaw tip", (x-.167, y, 1.315), (.075, .065, .040), "steel", "Tool", bevel=.012, rotation=(0, .35, 0))
        self.box("Wrench moving jaw tip", (x+.105, y, 1.285), (.062, .060, .035), "steel", "Tool", bevel=.010, rotation=(0, -.30, 0))
        self.torus("Wrench thumb wheel", (x+.005, y-.037, 1.175), .027, .008, "brass", "Tool",
                   rotation=(math.pi/2, 0, 0), major_segments=18, minor_segments=6)
        # Little personality bell under the head.
        self.torus("Wrench bell ring", (x-.115, y, 1.120), .018, .005, "brass", "Tool", major_segments=14, minor_segments=5)
        self.cyl("Wrench bell", (x-.115, y, 1.080), .024, .045, "brass", "Tool", vertices=16)
        self.ball("Wrench bell clapper", (x-.115, y, 1.052), (.008, .008, .008), "iron", "Tool", segments=12, rings=8)

    def detail(self):
        # Distinctive small salvage details, not random triangle noise.
        self.box("Smiley knee patch", (.105, -.086, .430), (.080, .012, .085), "shirt", "Thigh.L", bevel=.006)
        self.box("Mug badge", (-.105, -.170, .575), (.070, .022, .092), "ivory", "Pelvis", bevel=.010)
        self.cyl("Mug handle ring", (-.060, -.180, .575), .025, .012, "steel", "Pelvis", axis=(0, -1, 0), vertices=18)
        for x in (-.132, .132):
            self.cyl("Belt tool handle", (x, -.170, .705), .012, .095, "rust" if x < 0 else "yellow", "Pelvis", vertices=12)
        # Nose bandage and tiny hat charm.
        self.box("Nose bandage", (-.012, -.193, 1.060), (.048, .010, .018), "shirt", "Head", bevel=.004, rotation=(0, 0, .12))
        self.torus("Hat charm ring", (.155, -.030, 1.245), .016, .004, "brass", "Head", major_segments=14, minor_segments=5)
        self.cyl("Hat smile charm", (.155, -.030, 1.205), .022, .009, "yellow", "Head", axis=(0, -1, 0), vertices=18)

    def build(self):
        self.skeleton_contract()
        self.face_and_head()
        self.torso_and_clothes()
        self.limbs()
        self.shoulder_and_pack()
        self.wrench()
        self.detail()


def create_rig(hero: Kettlejack):
    data = bpy.data.armatures.new("Kettlejack_Skeleton")
    arm = bpy.data.objects.new("Kettlejack_Rig", data)
    bpy.context.collection.objects.link(arm)
    bpy.context.view_layer.objects.active = arm
    arm.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    for name, (head, tail, parent) in hero.bones.items():
        bone = data.edit_bones.new(name)
        bone.head, bone.tail = head, tail
        if parent:
            bone.parent = data.edit_bones[parent]
    bpy.ops.object.mode_set(mode="OBJECT")
    arm.select_set(False)
    arm.show_in_front = True
    data.display_type = "STICK"
    arm["coordinate_system"] = "Blender Z-up / glTF Y-up"
    arm["binding"] = "Rigid stylized shells with overlapping clothing joint covers"
    arm["donor"] = json.dumps(DONOR, sort_keys=True)
    return arm


def retain_and_join(hero: Kettlejack, arm):
    source = bpy.data.collections.new("SOURCE_editable_parts")
    bpy.context.scene.collection.children.link(source)
    working = []
    for obj in hero.parts:
        # Retain an editable geometry copy in the .blend source before skin assembly.
        copy = obj.copy()
        copy.data = obj.data.copy()
        source.objects.link(copy)
        for col in list(copy.users_collection):
            if col != source:
                col.objects.unlink(copy)
        copy.hide_render = True
        copy.hide_viewport = True

        bpy.context.view_layer.objects.active = obj
        obj.select_set(True)
        bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
        obj.select_set(False)
        group = obj.vertex_groups.new(name=obj["axm_bone"])
        group.add(list(range(len(obj.data.vertices))), 1.0, "REPLACE")
        working.append(obj)

    bpy.ops.object.select_all(action="DESELECT")
    for obj in working:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = working[0]
    bpy.ops.object.join()
    mesh = bpy.context.object
    mesh.name = ASSET_NAME
    mesh.data.name = f"{ASSET_NAME}_Surface"
    mesh.parent = arm
    modifier = mesh.modifiers.new("Kettlejack skeletal skin", "ARMATURE")
    modifier.object = arm
    for poly in mesh.data.polygons:
        poly.use_smooth = True
    return mesh


def reset_pose(arm):
    for bone in arm.pose.bones:
        bone.rotation_mode = "XYZ"
        bone.rotation_euler = (0, 0, 0)
        bone.location = (0, 0, 0)
        bone.scale = (1, 1, 1)


def rotate(arm, bone, *, x=0, y=0, z=0):
    b = arm.pose.bones[bone]
    b.rotation_mode = "XYZ"
    b.rotation_euler = tuple(math.radians(v) for v in (x, y, z))


def locate(arm, bone, xyz):
    arm.pose.bones[bone].location = xyz


def key_all(arm, frame):
    for bone in arm.pose.bones:
        bone.keyframe_insert("rotation_euler", frame=frame)
        bone.keyframe_insert("location", frame=frame)


def pose_idle(arm, phase):
    reset_pose(arm)
    breathe = math.sin(math.tau * phase)
    rotate(arm, "UpperArm.L", z=-4 + 2*breathe)
    rotate(arm, "UpperArm.R", z=5 - 2*breathe)
    rotate(arm, "Forearm.R", x=-10 - 3*breathe)
    rotate(arm, "Head", z=2*breathe, x=-1*breathe)
    rotate(arm, "ScarfTail", y=5*breathe)
    rotate(arm, "Tool", x=2*breathe)
    locate(arm, "Pelvis", (0, 0, .006*(1+breathe)))


def pose_run(arm, phase):
    reset_pose(arm)
    swing = math.sin(math.tau*phase)
    swing2 = math.sin(math.tau*phase + math.pi)
    rotate(arm, "Thigh.L", x=38*swing)
    rotate(arm, "Thigh.R", x=38*swing2)
    rotate(arm, "Shin.L", x=max(0, -55*swing))
    rotate(arm, "Shin.R", x=max(0, -55*swing2))
    rotate(arm, "UpperArm.L", x=-28*swing, z=-5)
    rotate(arm, "UpperArm.R", x=-28*swing2, z=5)
    rotate(arm, "Forearm.L", x=-14*swing)
    rotate(arm, "Forearm.R", x=-14*swing2)
    rotate(arm, "Chest", x=8, z=4*swing)
    rotate(arm, "Head", x=-4, z=-2*swing)
    rotate(arm, "ScarfTail", x=-12 + 7*swing)
    rotate(arm, "Tool", x=5*swing)
    locate(arm, "Root", (0, 0, .025*(1-math.cos(math.tau*phase*2))))


def pose_jump(arm, phase):
    reset_pose(arm)
    arc = math.sin(math.pi*phase)
    locate(arm, "Root", (0, 0, .26*arc))
    rotate(arm, "Thigh.L", x=-30 + 50*phase)
    rotate(arm, "Thigh.R", x=-18 - 42*phase)
    rotate(arm, "Shin.L", x=58*arc)
    rotate(arm, "Shin.R", x=48*arc)
    rotate(arm, "UpperArm.L", z=-65*arc, x=-18*arc)
    rotate(arm, "UpperArm.R", z=58*arc, x=12*arc)
    rotate(arm, "Forearm.R", x=-30*arc)
    rotate(arm, "ScarfTail", x=-32*arc)
    rotate(arm, "Tool", z=10*arc)


def pose_attack(arm, phase):
    reset_pose(arm)
    # 0 -> anticipation, .5 strike, 1 recovery.
    if phase <= .45:
        a = phase/.45
        rotate(arm, "UpperArm.R", x=-35*a, y=-55*a, z=20*a)
        rotate(arm, "Forearm.R", x=-55*a, z=-20*a)
        rotate(arm, "Chest", z=-18*a)
        rotate(arm, "Tool", x=55*a, y=-20*a)
    else:
        a = (phase-.45)/.55
        strike = math.sin(math.pi*min(1, a*1.25))
        rotate(arm, "UpperArm.R", x=-35*(1-a)+72*strike, y=-55*(1-a)+55*strike, z=20*(1-a)-18*strike)
        rotate(arm, "Forearm.R", x=-55*(1-a)+45*strike, z=-20*(1-a)-30*strike)
        rotate(arm, "Chest", z=-18*(1-a)+28*strike)
        rotate(arm, "Tool", x=55*(1-a)-105*strike, y=-20*(1-a))
    rotate(arm, "UpperArm.L", z=-12)
    rotate(arm, "Head", z=-5 + 8*phase)


def pose_victory(arm, phase):
    reset_pose(arm)
    a = math.sin(math.pi*phase)
    rotate(arm, "UpperArm.L", z=-82*a, x=-20*a)
    rotate(arm, "Forearm.L", x=-65*a)
    rotate(arm, "UpperArm.R", z=70*a, x=10*a)
    rotate(arm, "Forearm.R", x=-45*a)
    rotate(arm, "Tool", z=-28*a)
    rotate(arm, "Head", z=-8*a, x=-5*a)
    rotate(arm, "Chest", z=5*a)
    rotate(arm, "Shin.R", x=45*a)
    locate(arm, "Root", (0, 0, .055*a))


def make_action(arm, name, frames, pose_fn):
    action = bpy.data.actions.new(name)
    action.use_fake_user = True
    arm.animation_data_create()
    arm.animation_data.action = action
    last = frames[-1]
    for frame in frames:
        phase = (frame - frames[0]) / max(1, last - frames[0])
        pose_fn(arm, phase)
        key_all(arm, frame)
    return action


def animations(arm):
    bpy.context.scene.render.fps = FPS
    actions = {
        "Idle": make_action(arm, "Idle", [1, 16, 31, 46, 61], pose_idle),
        "Run": make_action(arm, "Run", [1, 7, 13, 19, 25], pose_run),
        "Jump": make_action(arm, "Jump", [1, 9, 17, 25, 33], pose_jump),
        "Wrench_Swing": make_action(arm, "Wrench_Swing", [1, 7, 13, 19, 27, 34], pose_attack),
        "Victory": make_action(arm, "Victory", [1, 11, 21, 31, 41], pose_victory),
    }
    arm.animation_data.action = actions["Idle"]
    bpy.context.scene.frame_set(1)
    return actions


def mesh_bounds(obj):
    corners = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]
    lo = [min(v[i] for v in corners) for i in range(3)]
    hi = [max(v[i] for v in corners) for i in range(3)]
    return lo, hi


def export(output: Path, arm, mesh, actions):
    # Retained editable Blender source first.
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
        export_animations=True, export_animation_mode="ACTIONS", export_merge_animation="ACTION",
        export_anim_slide_to_zero=True, export_force_sampling=True,
        export_yup=True, export_extras=True, export_tangents=True,
        export_cameras=False, export_lights=False, export_materials="EXPORT",
    )
    lo, hi = mesh_bounds(mesh)
    manifest = {
        "schema": SCHEMA,
        "asset_id": "kettlejack",
        "name": "Kettlejack",
        "coordinate_system": {"blender": "Z-up/-Y-forward", "gltf": "Y-up/+Z-forward", "units": "metres"},
        "donor": DONOR,
        "source": {"kind": "authored interpretation of generated Kettlejack concept", "image_projection": False,
                   "hidden_surfaces_inferred": True},
        "bounds_blender_m": {"min": lo, "max": hi, "height": hi[2]-lo[2]},
        "bones": [{"name": name, "parent": parent} for name, (_h, _t, parent) in hero.bones.items()],
        "clips": [
            {"name": "Idle", "frames": [1, 61], "loop": True, "duration_s": 60/FPS},
            {"name": "Run", "frames": [1, 25], "loop": True, "duration_s": 24/FPS},
            {"name": "Jump", "frames": [1, 33], "loop": False, "duration_s": 32/FPS},
            {"name": "Wrench_Swing", "frames": [1, 34], "loop": False, "duration_s": 33/FPS},
            {"name": "Victory", "frames": [1, 41], "loop": False, "duration_s": 40/FPS},
        ],
        "exports": {
            "glb": {"path": glb.name, "bytes": glb.stat().st_size, "sha256": sha(glb)},
            "blend": {"path": blend.name, "bytes": blend.stat().st_size, "sha256": sha(blend)},
        },
        "material_names": sorted({slot.material.name for slot in mesh.material_slots if slot.material}),
        "triangle_count": len(mesh.data.loop_triangles) if mesh.data.loop_triangles else None,
        "truth": {
            "real_geometry": True, "real_armature": True, "real_skin_weights": True,
            "real_animation_actions": True, "reference_pixel_faithful": False,
            "visual_acceptance": "REQUIRED", "game_engine_integration": "REQUIRED",
            "automatic_genome_mutation": False, "automatic_canon": False,
        },
    }
    save_json(output / "character-manifest.json", manifest)
    return manifest


def main():
    args = parse_args()
    output = Path(args.output).resolve()
    if output.exists():
        raise FileExistsError(f"Kettlejack foundry output must be new: {output}")
    output.mkdir(parents=True)
    clear_scene()
    global hero
    hero = Kettlejack(output)
    hero.build()
    arm = create_rig(hero)
    mesh = retain_and_join(hero, arm)
    mesh.data.calc_loop_triangles()
    actions = animations(arm)
    manifest = export(output, arm, mesh, actions)
    print(json.dumps({
        "status": "BUILT_VISUAL_REVIEW_REQUIRED",
        "asset": manifest["asset_id"],
        "bones": len(manifest["bones"]),
        "clips": [row["name"] for row in manifest["clips"]],
        "height_m": manifest["bounds_blender_m"]["height"],
        "glb": manifest["exports"]["glb"],
    }, sort_keys=True))


if __name__ == "__main__":
    main()
