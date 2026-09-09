extends SceneTree

const ASSET_PATH: String = "res://generated/sentinel_hm08_face_motion_v0_1.gltf"
const RECEIPT_PATH: String = "res://godot-face-motion-import-receipt.json"
const TARGETS: Array[String] = [
    "left_blink",
    "right_blink",
    "left_brow_raise",
    "right_brow_raise",
    "smile",
    "frown",
    "jaw_open",
]
const CLIPS: Array[String] = ["blink_test", "smile_test", "jaw_open_test"]

func write_receipt(receipt: Dictionary) -> void:
    var file: FileAccess = FileAccess.open(RECEIPT_PATH, FileAccess.WRITE)
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

func collect_nodes(node: Node, meshes: Array[MeshInstance3D], players: Array[AnimationPlayer]) -> void:
    if node is MeshInstance3D:
        meshes.append(node as MeshInstance3D)
    if node is AnimationPlayer:
        players.append(node as AnimationPlayer)
    for child: Node in node.get_children():
        collect_nodes(child, meshes, players)

func has_clip(actual_names: Array[String], expected: String) -> bool:
    for actual: String in actual_names:
        if actual == expected or actual.ends_with("/" + expected):
            return true
    return false

func _initialize() -> void:
    var receipt: Dictionary = {
        "schema": "axm.game-assets.godot-hm08-face-motion.v0.1",
        "asset": ASSET_PATH,
        "expected_targets": TARGETS,
        "expected_clips": CLIPS,
        "truth": "Real Godot import/runtime evidence that the hm08 motion-observer glTF exposes the authored blend shapes and morph-weight clips. This does not grade facial acting, anatomy or beauty."
    }
    if not FileAccess.file_exists(ASSET_PATH):
        fail("hm08 face-motion glTF does not exist", receipt)
        return

    var document: GLTFDocument = GLTFDocument.new()
    var state: GLTFState = GLTFState.new()
    var error: int = document.append_from_file(ASSET_PATH, state)
    receipt["append_from_file_error"] = error
    if error != OK:
        fail("Godot rejected hm08 face-motion glTF", receipt)
        return

    var instance: Node = document.generate_scene(state)
    if instance == null:
        fail("Godot generated no hm08 face-motion scene", receipt)
        return

    var mesh_nodes: Array[MeshInstance3D] = []
    var animation_players: Array[AnimationPlayer] = []
    collect_nodes(instance, mesh_nodes, animation_players)
    if mesh_nodes.is_empty():
        instance.free()
        fail("Godot scene contains no MeshInstance3D", receipt)
        return

    var observed_targets: Array[String] = []
    var runtime_weight_receipts: Dictionary = {}
    var total_surfaces: int = 0
    var total_vertices: int = 0
    var total_indices: int = 0
    for mesh_node: MeshInstance3D in mesh_nodes:
        if mesh_node.mesh == null:
            continue
        var mesh: Mesh = mesh_node.mesh
        total_surfaces += mesh.get_surface_count()
        for surface: int in range(mesh.get_surface_count()):
            total_vertices += mesh.surface_get_array_len(surface)
            total_indices += mesh.surface_get_array_index_len(surface)
        for index: int in range(mesh.get_blend_shape_count()):
            var target_name: String = str(mesh.get_blend_shape_name(index))
            if not observed_targets.has(target_name):
                observed_targets.append(target_name)
            var property_path: String = "blend_shapes/" + target_name
            mesh_node.set(property_path, 0.5)
            var observed_weight: Variant = mesh_node.get(property_path)
            runtime_weight_receipts[target_name] = observed_weight
            mesh_node.set(property_path, 0.0)

    observed_targets.sort()
    var expected_sorted: Array[String] = TARGETS.duplicate()
    expected_sorted.sort()
    receipt["observed_targets"] = observed_targets
    receipt["runtime_weight_receipts"] = runtime_weight_receipts
    receipt["mesh_instances"] = mesh_nodes.size()
    receipt["surfaces"] = total_surfaces
    receipt["vertices"] = total_vertices
    receipt["indices"] = total_indices
    if observed_targets != expected_sorted:
        instance.free()
        fail("Godot blend-shape target set differs from authored target set", receipt)
        return
    for target: String in TARGETS:
        if not runtime_weight_receipts.has(target):
            instance.free()
            fail("Missing runtime blend-shape property for %s" % target, receipt)
            return
        if abs(float(runtime_weight_receipts[target]) - 0.5) > 0.0001:
            instance.free()
            fail("Godot blend-shape property did not accept runtime weight for %s" % target, receipt)
            return

    var animation_names: Array[String] = []
    for player: AnimationPlayer in animation_players:
        for animation_name: StringName in player.get_animation_list():
            var value: String = str(animation_name)
            if not animation_names.has(value):
                animation_names.append(value)
    animation_names.sort()
    receipt["animation_players"] = animation_players.size()
    receipt["animation_names"] = animation_names
    for clip: String in CLIPS:
        if not has_clip(animation_names, clip):
            instance.free()
            fail("Godot did not expose morph-weight clip %s" % clip, receipt)
            return

    receipt["godot_version"] = Engine.get_version_info()
    receipt["status"] = "pass"
    write_receipt(receipt)
    print("AXM GODOT HM08 FACE MOTION PASS ", JSON.stringify(receipt))
    instance.free()
    quit(0)
