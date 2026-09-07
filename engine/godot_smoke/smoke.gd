extends SceneTree

const ASSET_PATH := "res://generated/sentinel_rifle.gltf"
const RECEIPT_PATH := "res://godot-receipt.json"

func fail(message: String, receipt: Dictionary = {}) -> void:
    receipt["status"] = "fail"
    receipt["failure"] = message
    receipt["godot_version"] = Engine.get_version_info()
    write_receipt(receipt)
    push_error(message)
    quit(1)

func write_receipt(receipt: Dictionary) -> void:
    var file := FileAccess.open(RECEIPT_PATH, FileAccess.WRITE)
    if file == null:
        push_error("Could not open receipt path: %s" % RECEIPT_PATH)
        return
    file.store_string(JSON.stringify(receipt, "  ") + "\n")
    file.close()

func collect_meshes(node: Node, out: Array[MeshInstance3D]) -> void:
    if node is MeshInstance3D:
        out.append(node as MeshInstance3D)
    for child in node.get_children():
        collect_meshes(child, out)

func _initialize() -> void:
    var receipt := {
        "schema": "axm.game-assets.godot-smoke.v0.1",
        "asset": ASSET_PATH,
        "truth": "Real Godot glTF parse/scene-instantiation evidence. This is not a visual-quality or performance proof."
    }

    if not FileAccess.file_exists(ASSET_PATH):
        fail("Generated glTF fixture does not exist", receipt)
        return

    for texture_path in [
        "res://generated/textures/base_color.png",
        "res://generated/textures/normal.png",
        "res://generated/textures/orm.png"
    ]:
        if not FileAccess.file_exists(texture_path):
            fail("Missing generated texture: %s" % texture_path, receipt)
            return

    var document := GLTFDocument.new()
    var state := GLTFState.new()
    var parse_error := document.append_from_file(ASSET_PATH, state)
    receipt["append_from_file_error"] = int(parse_error)
    if parse_error != OK:
        fail("Godot GLTFDocument rejected asset with error %s" % parse_error, receipt)
        return

    var instance := document.generate_scene(state)
    if instance == null:
        fail("Godot parsed glTF but could not generate a scene", receipt)
        return

    var mesh_nodes: Array[MeshInstance3D] = []
    collect_meshes(instance, mesh_nodes)
    if mesh_nodes.is_empty():
        fail("Generated Godot scene contains no MeshInstance3D", receipt)
        return

    var total_surfaces := 0
    var total_vertices := 0
    var total_indices := 0
    var material_surfaces := 0
    var nonzero_aabbs := 0
    var materials: Array[String] = []

    for mesh_node in mesh_nodes:
        var mesh := mesh_node.mesh
        if mesh == null:
            continue
        var aabb := mesh.get_aabb()
        if aabb.size.length() > 0.0:
            nonzero_aabbs += 1
        total_surfaces += mesh.get_surface_count()
        for surface in range(mesh.get_surface_count()):
            total_vertices += mesh.surface_get_array_len(surface)
            total_indices += mesh.surface_get_array_index_len(surface)
            var material := mesh.surface_get_material(surface)
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
