extends SceneTree

const ASSET_PATH: String = "res://generated/kettlejack_game_character_v0_1.gltf"
const RECEIPT_PATH: String = "res://godot-kettlejack-import-receipt.json"
const REQUIRED_CLIPS := ["idle", "run", "jump", "wrench_swing", "victory"]

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
        "schema": "axm.game-assets.godot-kettlejack-import/v0.1",
        "asset": ASSET_PATH,
        "required_clips": REQUIRED_CLIPS,
        "truth": "Real Godot 4.7.2 import evidence for the generated Kettlejack multi-material skinned glTF. It proves parseable surfaces, materials, skeleton bones and named animation clips. It does not prove final deformation quality, gameplay controller behavior, visual equivalence to concept art, performance, release readiness or CANON."
    }
    if not FileAccess.file_exists(ASSET_PATH):
        fail("Kettlejack glTF missing", receipt)
        return

    var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(ASSET_PATH))
    if not (parsed is Dictionary):
        fail("Kettlejack glTF is not readable JSON", receipt)
        return
    var gltf: Dictionary = parsed as Dictionary
    var image_uris: Array[String] = []
    for image_value: Variant in gltf.get("images", []) as Array:
        if image_value is Dictionary:
            var uri := str((image_value as Dictionary).get("uri", ""))
            if uri.is_empty() or uri.contains("://"):
                fail("Kettlejack image URI invalid or remote: %s" % uri, receipt)
                return
            if not FileAccess.file_exists(ASSET_PATH.get_base_dir().path_join(uri)):
                fail("Missing Kettlejack texture: %s" % uri, receipt)
                return
            image_uris.append(uri)
    receipt["declared_external_images"] = image_uris

    var document := GLTFDocument.new()
    var state := GLTFState.new()
    var error := document.append_from_file(ASSET_PATH, state)
    receipt["append_from_file_error"] = error
    if error != OK:
        fail("Godot rejected Kettlejack glTF", receipt)
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
    var vertices := 0
    var indices := 0
    var material_surfaces := 0
    for mesh_node: MeshInstance3D in meshes:
        if mesh_node.mesh == null:
            continue
        surfaces += mesh_node.mesh.get_surface_count()
        for surface: int in range(mesh_node.mesh.get_surface_count()):
            vertices += mesh_node.mesh.surface_get_array_len(surface)
            indices += mesh_node.mesh.surface_get_array_index_len(surface)
            if mesh_node.mesh.surface_get_material(surface) != null:
                material_surfaces += 1

    var bone_count := 0
    for skeleton: Skeleton3D in skeletons:
        bone_count = max(bone_count, skeleton.get_bone_count())

    var clips: Array[String] = []
    for player: AnimationPlayer in players:
        for animation_name: StringName in player.get_animation_list():
            var label := str(animation_name)
            if not clips.has(label):
                clips.append(label)
    clips.sort()

    receipt["mesh_instances"] = meshes.size()
    receipt["surfaces"] = surfaces
    receipt["vertices"] = vertices
    receipt["indices"] = indices
    receipt["material_surfaces"] = material_surfaces
    receipt["skeleton_nodes"] = skeletons.size()
    receipt["max_bone_count"] = bone_count
    receipt["animation_players"] = players.size()
    receipt["clips"] = clips
    receipt["godot_version"] = Engine.get_version_info()

    if meshes.is_empty() or surfaces < 8 or vertices <= 0 or indices <= 0:
        fail("Kettlejack mesh structure below proving minimum", receipt)
        return
    if material_surfaces != surfaces:
        fail("Kettlejack imported surface missing material", receipt)
        return
    if skeletons.is_empty() or bone_count < 23:
        fail("Kettlejack skeleton did not import with expected bones", receipt)
        return
    for required: String in REQUIRED_CLIPS:
        if not clips.has(required):
            fail("Kettlejack missing imported clip: %s" % required, receipt)
            return

    receipt["status"] = "pass"
    write_receipt(receipt)
    print("AXM GODOT KETTLEJACK IMPORT PASS ", JSON.stringify(receipt))
    instance.free()
    quit(0)
