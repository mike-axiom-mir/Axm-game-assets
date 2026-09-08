extends SceneTree

const ASSET_PATH: String = "res://generated/sentinel_hm08_face_candidate_v0_1.gltf"
const RECEIPT_PATH: String = "res://godot-face-eyes-import-receipt.json"

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
        "schema": "axm.game-assets.godot-face-eyes-import.v0.1",
        "asset": ASSET_PATH,
        "truth": "Real Godot import evidence for the layered hm08 face+eyes A/B candidate. It validates structure/material presence, not eye fit or beauty."
    }
    if not FileAccess.file_exists(ASSET_PATH):
        fail("Face+eyes glTF does not exist", receipt)
        return

    var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(ASSET_PATH))
    if not (parsed is Dictionary):
        fail("Face+eyes glTF is not readable JSON", receipt)
        return
    var gltf: Dictionary = parsed as Dictionary
    var image_uris: Array[String] = []
    for image_value: Variant in gltf.get("images", []) as Array:
        if image_value is Dictionary:
            var uri: String = str((image_value as Dictionary).get("uri", ""))
            if not uri.is_empty() and not uri.begins_with("data:"):
                image_uris.append(uri)
    for uri: String in image_uris:
        if uri.contains("://"):
            fail("Face+eyes evidence forbids remote image URI", receipt)
            return
        if not FileAccess.file_exists(ASSET_PATH.get_base_dir().path_join(uri)):
            fail("Missing face+eyes texture: %s" % uri, receipt)
            return
    receipt["declared_external_images"] = image_uris

    var document: GLTFDocument = GLTFDocument.new()
    var state: GLTFState = GLTFState.new()
    var error: int = document.append_from_file(ASSET_PATH, state)
    receipt["append_from_file_error"] = error
    if error != OK:
        fail("Godot rejected face+eyes glTF", receipt)
        return
    var instance: Node = document.generate_scene(state)
    if instance == null:
        fail("Godot generated no face+eyes scene", receipt)
        return

    var mesh_nodes: Array[MeshInstance3D] = []
    collect_meshes(instance, mesh_nodes)
    var surfaces: int = 0
    var vertices: int = 0
    var indices: int = 0
    var material_surfaces: int = 0
    var material_classes: Array[String] = []
    for mesh_node: MeshInstance3D in mesh_nodes:
        if mesh_node.mesh == null:
            continue
        surfaces += mesh_node.mesh.get_surface_count()
        for surface: int in range(mesh_node.mesh.get_surface_count()):
            vertices += mesh_node.mesh.surface_get_array_len(surface)
            indices += mesh_node.mesh.surface_get_array_index_len(surface)
            var material: Material = mesh_node.mesh.surface_get_material(surface)
            if material != null:
                material_surfaces += 1
                material_classes.append(material.get_class())
    receipt["mesh_instances"] = mesh_nodes.size()
    receipt["surfaces"] = surfaces
    receipt["vertices"] = vertices
    receipt["indices"] = indices
    receipt["material_surfaces"] = material_surfaces
    receipt["material_classes"] = material_classes
    receipt["godot_version"] = Engine.get_version_info()
    if mesh_nodes.is_empty() or surfaces != 5 or material_surfaces != 5 or vertices <= 0 or indices <= 0:
        fail("Layered face+eyes scene failed expected five-surface structure", receipt)
        return
    receipt["status"] = "pass"
    write_receipt(receipt)
    print("AXM GODOT FACE EYES IMPORT PASS ", JSON.stringify(receipt))
    instance.free()
    quit(0)
