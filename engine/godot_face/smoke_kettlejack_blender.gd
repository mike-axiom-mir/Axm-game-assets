extends SceneTree

const ASSET_PATH := "res://generated_blender/Kettlejack_game_character.glb"
const RECEIPT_PATH := "res://godot-kettlejack-blender-receipt.json"
const REQUIRED_CLIPS := ["Idle", "Run", "Jump", "Wrench_Swing", "Victory"]

func write_receipt(receipt: Dictionary) -> void:
    var file := FileAccess.open(RECEIPT_PATH, FileAccess.WRITE)
    if file != null:
        file.store_string(JSON.stringify(receipt, "  ") + "\n")
        file.close()

func fail(message: String, receipt: Dictionary) -> void:
    receipt["status"] = "fail"
    receipt["failure"] = message
    receipt["godot_version"] = Engine.get_version_info()
    write_receipt(receipt)
    push_error(message)
    quit(1)

func collect(node: Node, meshes: Array[MeshInstance3D], skeletons: Array[Skeleton3D], players: Array[AnimationPlayer]) -> void:
    if node is MeshInstance3D:
        meshes.append(node as MeshInstance3D)
    if node is Skeleton3D:
        skeletons.append(node as Skeleton3D)
    if node is AnimationPlayer:
        players.append(node as AnimationPlayer)
    for child: Node in node.get_children():
        collect(child, meshes, skeletons, players)

func _initialize() -> void:
    var receipt: Dictionary = {
        "schema": "axm.game-assets.godot-kettlejack-blender-import/v0.1",
        "asset": ASSET_PATH,
        "required_clips": REQUIRED_CLIPS,
        "truth": "Real Godot 4.7.2 import evidence for the Blender-foundry Kettlejack GLB. It proves surfaces, materials, skeleton and named animation clips are consumable. It does not prove final visual quality, controller behavior, performance, release status or CANON."
    }
    if not FileAccess.file_exists(ASSET_PATH):
        fail("Blender-foundry Kettlejack GLB missing", receipt)
        return
    var document := GLTFDocument.new()
    var state := GLTFState.new()
    var error := document.append_from_file(ASSET_PATH, state)
    receipt["append_from_file_error"] = error
    if error != OK:
        fail("Godot rejected Blender-foundry Kettlejack GLB", receipt)
        return
    var instance := document.generate_scene(state)
    if instance == null:
        fail("Godot generated no Kettlejack scene", receipt)
        return

    var meshes: Array[MeshInstance3D] = []
    var skeletons: Array[Skeleton3D] = []
    var players: Array[AnimationPlayer] = []
    collect(instance, meshes, skeletons, players)
    var surfaces := 0
    var material_surfaces := 0
    var vertices := 0
    var indices := 0
    for mesh_node in meshes:
        if mesh_node.mesh == null:
            continue
        surfaces += mesh_node.mesh.get_surface_count()
        for surface in range(mesh_node.mesh.get_surface_count()):
            vertices += mesh_node.mesh.surface_get_array_len(surface)
            indices += mesh_node.mesh.surface_get_array_index_len(surface)
            if mesh_node.mesh.surface_get_material(surface) != null:
                material_surfaces += 1
    var max_bones := 0
    for skeleton in skeletons:
        max_bones = maxi(max_bones, skeleton.get_bone_count())
    var clips: Array[String] = []
    for player in players:
        for library_name in player.get_animation_library_list():
            var library := player.get_animation_library(library_name)
            for animation_name in library.get_animation_list():
                if animation_name != "RESET" and not clips.has(animation_name):
                    clips.append(animation_name)
    clips.sort()
    for required in REQUIRED_CLIPS:
        if not clips.has(required):
            fail("Missing required clip: %s; imported=%s" % [required, clips], receipt)
            instance.free()
            return
    receipt["mesh_instances"] = meshes.size()
    receipt["surfaces"] = surfaces
    receipt["material_surfaces"] = material_surfaces
    receipt["vertices"] = vertices
    receipt["indices"] = indices
    receipt["skeleton_nodes"] = skeletons.size()
    receipt["max_bone_count"] = max_bones
    receipt["animation_players"] = players.size()
    receipt["clips"] = clips
    receipt["godot_version"] = Engine.get_version_info()
    if meshes.is_empty() or surfaces < 6 or material_surfaces != surfaces or vertices <= 0 or indices <= 0 or max_bones < 20:
        fail("Imported Kettlejack failed minimum game-character structure", receipt)
        instance.free()
        return
    receipt["status"] = "pass"
    write_receipt(receipt)
    print("AXM GODOT BLENDER KETTLEJACK IMPORT PASS ", JSON.stringify(receipt))
    instance.free()
    quit(0)
