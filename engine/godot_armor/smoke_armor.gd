extends SceneTree

const BODY_PATH := "res://generated/body-control.gltf"
const ARMOR_PATH := "res://generated/sentinel_armor_v0_1.gltf"
const RECEIPT_PATH := "res://godot-armor-import-receipt.json"

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

func import_gltf(path: String, receipt: Dictionary, label: String) -> Node:
    if not FileAccess.file_exists(path):
        fail("Missing %s glTF" % label, receipt)
        return null
    var document := GLTFDocument.new()
    var state := GLTFState.new()
    var err := document.append_from_file(path, state)
    receipt[label + "_append_error"] = err
    if err != OK:
        fail("Godot rejected %s glTF" % label, receipt)
        return null
    var scene := document.generate_scene(state)
    if scene == null:
        fail("Godot generated no %s scene" % label, receipt)
        return null
    return scene

func collect_meshes(node: Node, out: Array[MeshInstance3D]) -> void:
    if node is MeshInstance3D:
        out.append(node as MeshInstance3D)
    for child: Node in node.get_children():
        collect_meshes(child, out)

func mesh_stats(node: Node) -> Dictionary:
    var meshes: Array[MeshInstance3D] = []
    collect_meshes(node, meshes)
    var surfaces := 0
    var material_surfaces := 0
    var vertices := 0
    var indices := 0
    var material_names: Array[String] = []
    for mesh_node in meshes:
        if mesh_node.mesh == null:
            continue
        for surface in range(mesh_node.mesh.get_surface_count()):
            surfaces += 1
            vertices += mesh_node.mesh.surface_get_array_len(surface)
            indices += mesh_node.mesh.surface_get_array_index_len(surface)
            var material := mesh_node.mesh.surface_get_material(surface)
            if material != null:
                material_surfaces += 1
                material_names.append(material.resource_name)
    return {
        "mesh_instances": meshes.size(),
        "surfaces": surfaces,
        "material_surfaces": material_surfaces,
        "vertices": vertices,
        "indices": indices,
        "material_names": material_names,
    }

func _initialize() -> void:
    var receipt: Dictionary = {
        "schema": "game-asset-forge.godot-sentinel-armor-import.v0.2",
        "body_asset": BODY_PATH,
        "armor_asset": ARMOR_PATH,
        "body_alias_rule": "body-control.gltf is copied from the exact glTF filename emitted by the current canonical full-body builder; its original binary/texture URIs remain beside it.",
        "truth": "Real Godot import structure for the current complete clothed Sentinel substrate plus independent semantic rigid-armor overlay. The test follows the canonical body builder instead of hard-coding a historical body version. It does not grade visual quality or deformation clearance."
    }
    var body := import_gltf(BODY_PATH, receipt, "body")
    if body == null:
        return
    var armor := import_gltf(ARMOR_PATH, receipt, "armor")
    if armor == null:
        body.free()
        return
    var body_stats := mesh_stats(body)
    var armor_stats := mesh_stats(armor)
    receipt["body"] = body_stats
    receipt["armor"] = armor_stats
    receipt["godot_version"] = Engine.get_version_info()
    if int(body_stats["surfaces"]) < 10 or int(body_stats["material_surfaces"]) != int(body_stats["surfaces"]):
        fail("Body substrate failed layered/material-complete import", receipt)
        return
    if int(armor_stats["surfaces"]) < 14 or int(armor_stats["material_surfaces"]) != int(armor_stats["surfaces"]):
        fail("Armor overlay failed semantic/material-complete import", receipt)
        return
    if int(armor_stats["vertices"]) <= 0 or int(armor_stats["indices"]) <= 0:
        fail("Armor overlay imported empty geometry", receipt)
        return
    receipt["status"] = "pass"
    write_receipt(receipt)
    print("GAME ASSET FORGE GODOT ARMOR IMPORT PASS ", JSON.stringify(receipt))
    body.free()
    armor.free()
    quit(0)
