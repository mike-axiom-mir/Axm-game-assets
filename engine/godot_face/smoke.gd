extends SceneTree

const ASSET_PATH: String = "res://generated/sentinel_hm08_face_candidate_v0_1.gltf"
const RECEIPT_PATH: String = "res://godot-face-import-receipt.json"

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

func collect_meshes(node: Node, out: Array[MeshInstance3D]) -> void:
    if node is MeshInstance3D:
        out.append(node as MeshInstance3D)
    for child: Node in node.get_children():
        collect_meshes(child, out)

func _initialize() -> void:
    var receipt: Dictionary = {
        "schema": "axm.game-assets.godot-face-import.v0.1",
        "asset": ASSET_PATH,
        "truth": "Real Godot import/scene-instantiation evidence for the hm08 Sentinel face snapshot. Not a face-quality judgment."
    }
    if not FileAccess.file_exists(ASSET_PATH):
        fail("Face glTF does not exist", receipt)
        return

    var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(ASSET_PATH))
    if not (parsed is Dictionary):
        fail("Face glTF is not readable JSON", receipt)
        return
    var gltf: Dictionary = parsed as Dictionary
    var declared_images: Array[String] = []
    for image_value: Variant in gltf.get("images", []) as Array:
        if image_value is Dictionary:
            var uri: String = str((image_value as Dictionary).get("uri", ""))
            if not uri.is_empty() and not uri.begins_with("data:"):
                declared_images.append(uri)
    for uri: String in declared_images:
        if uri.contains("://"):
            fail("Face engine evidence forbids remote image URI: %s" % uri, receipt)
            return
        var resolved: String = ASSET_PATH.get_base_dir().path_join(uri)
        if not FileAccess.file_exists(resolved):
            fail("Missing face texture: %s" % resolved, receipt)
            return
    receipt["declared_external_images"] = declared_images

    var document: GLTFDocument = GLTFDocument.new()
    var state: GLTFState = GLTFState.new()
    var parse_error: int = document.append_from_file(ASSET_PATH, state)
    receipt["append_from_file_error"] = parse_error
    if parse_error != OK:
        fail("Godot rejected face glTF with error %s" % parse_error, receipt)
        return
    var instance: Node = document.generate_scene(state)
    if instance == null:
        fail("Godot parsed face glTF but generated no scene", receipt)
        return

    var mesh_nodes: Array[MeshInstance3D] = []
    collect_meshes(instance, mesh_nodes)
    var surfaces: int = 0
    var vertices: int = 0
    var indices: int = 0
    var material_surfaces: int = 0
    var materials: Array[String] = []
    var nonzero_aabbs: int = 0
    for mesh_node: MeshInstance3D in mesh_nodes:
        var mesh: Mesh = mesh_node.mesh
        if mesh == null:
            continue
        if mesh.get_aabb().size.length() > 0.0:
            nonzero_aabbs += 1
        surfaces += mesh.get_surface_count()
        for surface: int in range(mesh.get_surface_count()):
            vertices += mesh.surface_get_array_len(surface)
            indices += mesh.surface_get_array_index_len(surface)
            var material: Material = mesh.surface_get_material(surface)
            if material != null:
                material_surfaces += 1
                materials.append(material.get_class())

    receipt["mesh_instances"] = mesh_nodes.size()
    receipt["surfaces"] = surfaces
    receipt["vertices"] = vertices
    receipt["indices"] = indices
    receipt["material_surfaces"] = material_surfaces
    receipt["material_classes"] = materials
    receipt["nonzero_aabbs"] = nonzero_aabbs
    receipt["godot_version"] = Engine.get_version_info()

    if mesh_nodes.is_empty() or surfaces != 1 or vertices <= 0 or indices <= 0 or material_surfaces != 1 or nonzero_aabbs <= 0:
        fail("Imported face scene failed structural expectations", receipt)
        return

    receipt["status"] = "pass"
    write_receipt(receipt)
    print("AXM GODOT FACE IMPORT PASS ", JSON.stringify(receipt))
    instance.free()
    quit(0)
