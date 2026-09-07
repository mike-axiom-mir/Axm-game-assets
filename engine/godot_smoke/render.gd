extends SceneTree

const ASSET_PATH: String = "res://generated/sentinel_rifle.gltf"
const RENDER_PATH: String = "res://godot-render.png"
const DEBUG_RENDER_PATH: String = "res://godot-render-debug.png"
const RECEIPT_PATH: String = "res://godot-render-receipt.json"
const SIZE: Vector2i = Vector2i(640, 640)
const CLEAR_COLOR: Color = Color(0.025, 0.032, 0.045, 1.0)

func write_receipt(receipt: Dictionary) -> void:
    var file: FileAccess = FileAccess.open(RECEIPT_PATH, FileAccess.WRITE)
    if file == null:
        push_error("Could not open render receipt path")
        return
    file.store_string(JSON.stringify(receipt, "  ") + "\n")
    file.close()

func fail(message: String, receipt: Dictionary = {}) -> void:
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

func transformed_aabb(local_aabb: AABB, transform: Transform3D) -> AABB:
    var p: Vector3 = local_aabb.position
    var s: Vector3 = local_aabb.size
    var corners: Array[Vector3] = [
        p,
        p + Vector3(s.x, 0.0, 0.0),
        p + Vector3(0.0, s.y, 0.0),
        p + Vector3(0.0, 0.0, s.z),
        p + Vector3(s.x, s.y, 0.0),
        p + Vector3(s.x, 0.0, s.z),
        p + Vector3(0.0, s.y, s.z),
        p + s,
    ]
    var first: Vector3 = transform * corners[0]
    var result: AABB = AABB(first, Vector3.ZERO)
    for index: int in range(1, corners.size()):
        result = result.expand(transform * corners[index])
    return result

func aggregate_mesh_bounds(root: Node) -> Dictionary:
    var meshes: Array[MeshInstance3D] = []
    collect_meshes(root, meshes)
    var have_bounds: bool = false
    var merged: AABB = AABB()
    var mesh_records: Array[Dictionary] = []
    for mesh_node: MeshInstance3D in meshes:
        var mesh: Mesh = mesh_node.mesh
        if mesh == null:
            continue
        var local_bounds: AABB = mesh.get_aabb()
        var world_bounds: AABB = transformed_aabb(local_bounds, mesh_node.global_transform)
        if not have_bounds:
            merged = world_bounds
            have_bounds = true
        else:
            merged = merged.merge(world_bounds)
        mesh_records.append({
            "name": mesh_node.name,
            "local_position": [local_bounds.position.x, local_bounds.position.y, local_bounds.position.z],
            "local_size": [local_bounds.size.x, local_bounds.size.y, local_bounds.size.z],
            "world_position": [world_bounds.position.x, world_bounds.position.y, world_bounds.position.z],
            "world_size": [world_bounds.size.x, world_bounds.size.y, world_bounds.size.z],
            "surfaces": mesh.get_surface_count(),
        })
    return {"have_bounds": have_bounds, "bounds": merged, "meshes": mesh_records}

func capture_metrics(viewport: SubViewport, path: String) -> Dictionary:
    var image: Image = viewport.get_texture().get_image()
    if image == null or image.is_empty():
        return {"status": "fail", "failure": "SubViewport produced no image"}
    var save_error: int = image.save_png(path)
    if save_error != OK:
        return {"status": "fail", "failure": "Could not save PNG", "save_error": save_error}

    var width: int = image.get_width()
    var height: int = image.get_height()
    var background: Color = image.get_pixel(2, 2)
    var sampled: int = 0
    var foreground: int = 0
    var min_luma: float = 1.0
    var max_luma: float = 0.0
    var luma_sum: float = 0.0
    for y: int in range(0, height, 2):
        for x: int in range(0, width, 2):
            var color: Color = image.get_pixel(x, y)
            var pixel_delta: float = absf(color.r - background.r) + absf(color.g - background.g) + absf(color.b - background.b)
            if pixel_delta > 0.055:
                foreground += 1
            var luma: float = color.r * 0.2126 + color.g * 0.7152 + color.b * 0.0722
            if luma < min_luma:
                min_luma = luma
            if luma > max_luma:
                max_luma = luma
            luma_sum += luma
            sampled += 1

    var coverage: float = float(foreground) / float(maxi(sampled, 1))
    var png_bytes: int = FileAccess.get_file_as_bytes(path).size()
    return {
        "status": "pass",
        "path": path,
        "width": width,
        "height": height,
        "png_bytes": png_bytes,
        "sampled_pixels": sampled,
        "foreground_pixels": foreground,
        "foreground_coverage": coverage,
        "luma_min": min_luma,
        "luma_max": max_luma,
        "luma_mean": luma_sum / float(maxi(sampled, 1)),
        "luma_range": max_luma - min_luma,
        "background_sample": [background.r, background.g, background.b, background.a],
    }

func add_debug_material_override(imported: Node) -> int:
    var meshes: Array[MeshInstance3D] = []
    collect_meshes(imported, meshes)
    var debug_material: StandardMaterial3D = StandardMaterial3D.new()
    debug_material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
    debug_material.albedo_color = Color(1.0, 0.08, 0.85, 1.0)
    debug_material.cull_mode = BaseMaterial3D.CULL_DISABLED
    for mesh_node: MeshInstance3D in meshes:
        mesh_node.material_override = debug_material
    return meshes.size()

func _initialize() -> void:
    var receipt: Dictionary = {
        "schema": "axm.game-assets.godot-render.v0.5",
        "asset": ASSET_PATH,
        "truth": "Real Godot-rendered screenshot and pixel evidence from an explicit SubViewport. Camera/light framing derives from imported world-space bounds. A debug-material render is diagnostic only and can never turn a failed production-material capture into a pass."
    }
    if not FileAccess.file_exists(ASSET_PATH):
        fail("Generated glTF fixture does not exist", receipt)
        return

    RenderingServer.set_default_clear_color(CLEAR_COLOR)

    var document: GLTFDocument = GLTFDocument.new()
    var state: GLTFState = GLTFState.new()
    var parse_error: int = document.append_from_file(ASSET_PATH, state)
    receipt["append_from_file_error"] = parse_error
    if parse_error != OK:
        fail("Godot GLTFDocument rejected render asset with error %s" % parse_error, receipt)
        return
    var imported: Node = document.generate_scene(state)
    if imported == null:
        fail("Godot parsed glTF but could not generate render scene", receipt)
        return

    var viewport: SubViewport = SubViewport.new()
    viewport.name = "AXM_Evidence_Viewport"
    viewport.size = SIZE
    viewport.own_world_3d = true
    viewport.transparent_bg = false
    viewport.render_target_clear_mode = SubViewport.CLEAR_MODE_ALWAYS
    viewport.render_target_update_mode = SubViewport.UPDATE_ALWAYS
    get_root().add_child(viewport)

    var scene_root: Node3D = Node3D.new()
    scene_root.name = "AXM_Render_Proof"
    viewport.add_child(scene_root)
    scene_root.add_child(imported)

    await process_frame
    var bounds_state: Dictionary = aggregate_mesh_bounds(imported)
    if not bool(bounds_state["have_bounds"]):
        fail("Imported Godot scene has no mesh bounds to frame", receipt)
        return
    var world_bounds: AABB = bounds_state["bounds"]
    if world_bounds.size.length() <= 1e-6:
        receipt["imported_meshes"] = bounds_state["meshes"]
        fail("Imported Godot scene bounds are effectively empty", receipt)
        return
    var center: Vector3 = world_bounds.get_center()
    var radius: float = maxf(world_bounds.size.length() * 0.5, 0.05)

    var environment: Environment = Environment.new()
    environment.background_mode = Environment.BG_COLOR
    environment.background_color = CLEAR_COLOR
    environment.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
    environment.ambient_light_color = Color(0.48, 0.52, 0.62, 1.0)
    environment.ambient_light_energy = 0.85
    var world_environment: WorldEnvironment = WorldEnvironment.new()
    world_environment.environment = environment
    scene_root.add_child(world_environment)

    var key: DirectionalLight3D = DirectionalLight3D.new()
    key.light_energy = 1.65
    key.rotation_degrees = Vector3(-48.0, -32.0, 0.0)
    key.shadow_enabled = true
    scene_root.add_child(key)

    var fill: OmniLight3D = OmniLight3D.new()
    fill.position = center + Vector3(-1.0, 0.8, 1.2).normalized() * radius * 2.2
    fill.omni_range = radius * 6.0
    fill.light_energy = 2.4
    scene_root.add_child(fill)

    var rim: OmniLight3D = OmniLight3D.new()
    rim.position = center + Vector3(1.2, 0.65, -1.0).normalized() * radius * 2.4
    rim.omni_range = radius * 6.0
    rim.light_energy = 2.0
    scene_root.add_child(rim)

    var camera: Camera3D = Camera3D.new()
    camera.fov = 42.0
    camera.near = 0.01
    camera.far = maxf(100.0, radius * 20.0)
    var camera_direction: Vector3 = Vector3(1.35, 0.62, 1.25).normalized()
    var framing_distance: float = radius / tan(deg_to_rad(camera.fov * 0.5)) * 1.38
    var camera_position: Vector3 = center + camera_direction * framing_distance
    # Godot 4.7 explicitly recommends look_at_from_position() when a Node3D
    # is not yet fully registered in its viewport tree. This avoids a silent
    # identity camera transform and therefore a clear-color-only capture.
    camera.look_at_from_position(camera_position, center, Vector3.UP)
    scene_root.add_child(camera)
    camera.make_current()

    receipt["imported_meshes"] = bounds_state["meshes"]
    receipt["world_bounds"] = {
        "position": [world_bounds.position.x, world_bounds.position.y, world_bounds.position.z],
        "size": [world_bounds.size.x, world_bounds.size.y, world_bounds.size.z],
        "center": [center.x, center.y, center.z],
        "radius": radius,
    }
    receipt["camera"] = {
        "position": [camera_position.x, camera_position.y, camera_position.z],
        "look_at": [center.x, center.y, center.z],
        "fov": camera.fov,
        "near": camera.near,
        "far": camera.far,
        "framing_distance": framing_distance,
    }

    for _frame: int in range(16):
        await process_frame

    receipt["active_camera"] = viewport.get_camera_3d() != null
    if viewport.get_camera_3d() == null:
        fail("SubViewport has no active Camera3D after framing", receipt)
        return

    var normal_metrics: Dictionary = capture_metrics(viewport, RENDER_PATH)
    receipt["render_target"] = {
        "kind": "SubViewport",
        "requested_width": SIZE.x,
        "requested_height": SIZE.y,
    }
    receipt["normal_render"] = normal_metrics
    receipt["godot_version"] = Engine.get_version_info()

    if str(normal_metrics.get("status", "fail")) != "pass":
        fail("Godot normal-material render capture failed", receipt)
        return

    var normal_width: int = int(normal_metrics["width"])
    var normal_height: int = int(normal_metrics["height"])
    var normal_png_bytes: int = int(normal_metrics["png_bytes"])
    var normal_coverage: float = float(normal_metrics["foreground_coverage"])
    var normal_luma_range: float = float(normal_metrics["luma_range"])

    receipt["render_target"]["actual_width"] = normal_width
    receipt["render_target"]["actual_height"] = normal_height

    var normal_failure: String = ""
    if normal_width != SIZE.x or normal_height != SIZE.y:
        normal_failure = "Unexpected SubViewport dimensions %sx%s" % [normal_width, normal_height]
    elif normal_png_bytes <= 1000:
        normal_failure = "Rendered PNG is unexpectedly small: %s bytes" % normal_png_bytes
    elif normal_coverage < 0.015:
        normal_failure = "Rendered asset coverage too small: %s" % normal_coverage
    elif normal_luma_range < 0.10:
        normal_failure = "Rendered image lacks visible contrast: %s" % normal_luma_range

    if normal_failure != "":
        var debug_meshes: int = add_debug_material_override(imported)
        for _frame: int in range(6):
            await process_frame
        var debug_metrics: Dictionary = capture_metrics(viewport, DEBUG_RENDER_PATH)
        receipt["diagnostic_render"] = {
            "authority": "diagnostic_only",
            "material": "unshaded_magenta_double_sided",
            "mesh_instances_overridden": debug_meshes,
            "metrics": debug_metrics,
            "interpretation": "If this debug render has foreground signal while the normal render does not, camera/world/geometry visibility is healthy and the remaining defect is in material/culling/shading. A diagnostic pass never overrides the normal-render failure."
        }
        fail(normal_failure, receipt)
        return

    receipt["status"] = "pass"
    write_receipt(receipt)
    print("AXM GODOT RENDER PASS ", JSON.stringify(receipt))
    viewport.queue_free()
    quit(0)
