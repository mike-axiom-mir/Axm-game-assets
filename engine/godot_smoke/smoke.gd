extends SceneTree

const ASSET_PATH: String = "res://generated/sentinel_rifle.gltf"
const RECEIPT_PATH: String = "res://godot-receipt.json"

func fail(message: String, receipt: Dictionary = {}) -> void:
    receipt["status"] = "fail"
    receipt["failure"] = message
    receipt["godot_version"] = Engine.get_version_info()
    write_receipt(receipt)
    push_error(message)
    quit(1)

func write_receipt(receipt: Dictionary) -> void:
    var file: FileAccess = FileAccess.open(RECEIPT_PATH, FileAccess.WRITE)
    if file == null:
        push_error("Could not open receipt path: %s" % RECEIPT_PATH)
        return
    file.store_string(JSON.stringify(receipt, "  ") + "\n")
    file.close()

func collect_meshes(node: Node, out: Array[MeshInstance3D]) -> void:
    if node is MeshInstance3D:
        out.append(node as MeshInstance3D)
    for child: Node in node.get_children():
        collect_meshes(child, out)

func declared_external_images(receipt: Dictionary) -> Array[String]:
    var text: String = FileAccess.get_file_as_string(ASSET_PATH)
    if text.is_empty():
        fail("Generated glTF fixture could not be read as JSON text", receipt)
        return []
    var parsed: Variant = JSON.parse_string(text)
    if not (parsed is Dictionary):
        fail("Generated glTF fixture is not a JSON object", receipt)
        return []
    var document: Dictionary = parsed as Dictionary
    var result: Array[String] = []
    var images_value: Variant = document.get("images", [])
    if not (images_value is Array):
        fail("glTF images member is not an array", receipt)
        return []
    for image_value: Variant in images_value as Array:
        if not (image_value is Dictionary):
            fail("glTF images array contains a non-object entry", receipt)
            return []
        var image: Dictionary = image_value as Dictionary
        var uri: String = str(image.get("uri", ""))
        # Empty URI is legal for bufferView-backed images. Data URIs are
        # self-contained. Only external file URIs need a filesystem check.
        if uri.is_empty() or uri.begins_with("data:"):
            continue
        result.append(uri)
    return result

func _initialize() -> void:
    var receipt: Dictionary = {
        "schema": "axm.game-assets.godot-smoke.v0.2",
        "asset": ASSET_PATH,
        "truth": "Real Godot glTF parse/scene-instantiation evidence. External image dependencies are validated from the glTF's declared image URIs rather than from a historical texture-folder convention. This is not a visual-quality or performance proof."
    }

    if not FileAccess.file_exists(ASSET_PATH):
        fail("Generated glTF fixture does not exist", receipt)
        return

    var image_uris: Array[String] = declared_external_images(receipt)
    if receipt.get("status") == "fail":
        return
    receipt["declared_external_images"] = image_uris
    var asset_dir: String = ASSET_PATH.get_base_dir()
    var resolved_images: Array[String] = []
    for uri: String in image_uris:
        # Current Forge deliveries use relative local URIs. Reject a remote URI
        # here rather than silently adding a network dependency to engine smoke.
        if uri.contains("://"):
            fail("Engine smoke does not allow network image URI: %s" % uri, receipt)
            return
        var resolved: String = asset_dir.path_join(uri)
        resolved_images.append(resolved)
        if not FileAccess.file_exists(resolved):
            fail("Missing glTF-declared image: %s" % resolved, receipt)
            return
    receipt["resolved_external_images"] = resolved_images

    var document: GLTFDocument = GLTFDocument.new()
    var state: GLTFState = GLTFState.new()
    var parse_error: int = document.append_from_file(ASSET_PATH, state)
    receipt["append_from_file_error"] = int(parse_error)
    if parse_error != OK:
        fail("Godot GLTFDocument rejected asset with error %s" % parse_error, receipt)
        return

    var instance: Node = document.generate_scene(state)
    if instance == null:
        fail("Godot parsed glTF but could not generate a scene", receipt)
        return

    var mesh_nodes: Array[MeshInstance3D] = []
    collect_meshes(instance, mesh_nodes)
    if mesh_nodes.is_empty():
        fail("Generated Godot scene contains no MeshInstance3D", receipt)
        return

    var total_surfaces: int = 0
    var total_vertices: int = 0
    var total_indices: int = 0
    var material_surfaces: int = 0
    var nonzero_aabbs: int = 0
    var materials: Array[String] = []

    for mesh_node: MeshInstance3D in mesh_nodes:
        var mesh: Mesh = mesh_node.mesh
        if mesh == null:
            continue
        var aabb: AABB = mesh.get_aabb()
        if aabb.size.length() > 0.0:
            nonzero_aabbs += 1
        total_surfaces += mesh.get_surface_count()
        for surface: int in range(mesh.get_surface_count()):
            total_vertices += mesh.surface_get_array_len(surface)
            total_indices += mesh.surface_get_array_index_len(surface)
            var material: Material = mesh.surface_get_material(surface)
            if material != null:
                material_surfaces += 1
                materials.append(material.get_class())

    receipt["mesh_instances"] = mesh_nodes.size()
    receipt["surfaces"] = total_surfaces
    receipt["vertices"] = total_vertices
    receipt["indices"] = total_indices
    receipt["material_surfaces"] = material_surfaces
    receipt["material_classes"] = materials
    receipt["nonzero_aabbs"] = nonzero_aabbs
    receipt["godot_version"] = Engine.get_version_info()

    if total_surfaces <= 0:
        fail("Imported scene has no mesh surfaces", receipt)
        return
    if total_vertices <= 0 or total_indices <= 0:
        fail("Imported mesh surfaces have no vertex/index data", receipt)
        return
    if material_surfaces <= 0:
        fail("Imported mesh surfaces contain no material", receipt)
        return
    if nonzero_aabbs <= 0:
        fail("Imported mesh bounds are empty", receipt)
        return

    receipt["status"] = "pass"
    write_receipt(receipt)
    print("AXM GODOT SMOKE PASS ", JSON.stringify(receipt))
    instance.free()
    quit(0)
