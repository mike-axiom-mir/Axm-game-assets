extends SceneTree

const ASSET_PATH: String = "res://generated/sentinel_rifle.gltf"
const RECEIPT_PATH: String = "res://godot-multiview-receipt.json"
const SIZE: Vector2i = Vector2i(640, 640)
const CLEAR_COLOR: Color = Color(0.025, 0.032, 0.045, 1.0)

func write_receipt(receipt: Dictionary) -> void:
    var file: FileAccess = FileAccess.open(RECEIPT_PATH, FileAccess.WRITE)
    if file == null:
        push_error("Could not open multiview receipt path")
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
    for mesh_node: MeshInstance3D in meshes:
        var mesh: Mesh = mesh_node.mesh
        if mesh == null:
            continue
        var world_bounds: AABB = transformed_aabb(mesh.get_aabb(), mesh_node.global_transform)
        if not have_bounds:
            merged = world_bounds
            have_bounds = true
        else:
            merged = merged.merge(world_bounds)
    return {"have_bounds": have_bounds, "bounds": merged, "mesh_instances": meshes.size()}

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
            var delta: float = absf(color.r - background.r) + absf(color.g - background.g) + absf(color.b - background.b)
            if delta > 0.055:
                foreground += 1
            var luma: float = color.r * 0.2126 + color.g * 0.7152 + color.b * 0.0722
            if luma < min_luma:
                min_luma = luma
            if luma > max_luma:
                max_luma = luma
            luma_sum += luma
            sampled += 1
    return {
        "status": "pass",
        "path": path,
        "width": width,
        "height": height,
        "png_bytes": FileAccess.get_file_as_bytes(path).size(),
        "sampled_pixels": sampled,
        "foreground_pixels": foreground,
        "foreground_coverage": float(foreground) / float(maxi(sampled, 1)),
        "luma_min": min_luma,
        "luma_max": max_luma,
        "luma_mean": luma_sum / float(maxi(sampled, 1)),
        "luma_range": max_luma - min_luma,
        "background_sample": [background.r, background.g, background.b, background.a],
    }

func _initialize() -> void:
    var receipt: Dictionary = {
        "schema": "axm.game-assets.godot-multiview.v0.1",
        "asset": ASSET_PATH,
        "truth": "Three real Godot capture views for close-inspection evidence. Camera choices and pixel metrics are deterministic capture facts only; they do not grade aesthetics."
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
        fail("Godot rejected multiview asset with error %s" % parse_error, receipt)
        return
    var imported: Node = document.generate_scene(state)
    if imported == null:
        fail("Godot could not generate multiview scene", receipt)
        return

    var viewport: SubViewport = SubViewport.new()
    viewport.name = "AXM_Multiview_Viewport"
    viewport.size = SIZE
    viewport.own_world_3d = true
    viewport.transparent_bg = false
    viewport.render_target_clear_mode = SubViewport.CLEAR_MODE_ALWAYS
    viewport.render_target_update_mode = SubViewport.UPDATE_ALWAYS
    get_root().add_child(viewport)

    var scene_root: Node3D = Node3D.new()
    viewport.add_child(scene_root)
    scene_root.add_child(imported)
    await process_frame

    var bounds_state: Dictionary = aggregate_mesh_bounds(imported)
    if not bool(bounds_state["have_bounds"]):
        fail("Imported scene has no bounds", receipt)
        return
    var world_bounds: AABB = bounds_state["bounds"]
    var center: Vector3 = world_bounds.get_center()
    var radius: float = maxf(world_bounds.size.length() * 0.5, 0.05)
    receipt["world_bounds"] = {
        "position": [world_bounds.position.x, world_bounds.position.y, world_bounds.position.z],
        "size": [world_bounds.size.x, world_bounds.size.y, world_bounds.size.z],
        "center": [center.x, center.y, center.z],
        "radius": radius,
        "mesh_instances": bounds_state["mesh_instances"],
    }

    var environment: Environment = Environment.new()
    environment.background_mode = Environment.BG_COLOR
    environment.background_color = CLEAR_COLOR
    environment.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
    environment.ambient_light_color = Color(0.45, 0.50, 0.59, 1.0)
    environment.ambient_light_energy = 0.78
    var world_environment: WorldEnvironment = WorldEnvironment.new()
    world_environment.environment = environment
    scene_root.add_child(world_environment)

    var key: DirectionalLight3D = DirectionalLight3D.new()
    key.light_energy = 1.55
    key.rotation_degrees = Vector3(-48.0, -32.0, 0.0)
    key.shadow_enabled = true
    scene_root.add_child(key)

    var fill: OmniLight3D = OmniLight3D.new()
    fill.position = center + Vector3(-1.0, 0.8, 1.2).normalized() * radius * 2.2
    fill.omni_range = radius * 6.0
    fill.light_energy = 2.25
    scene_root.add_child(fill)

    var rim: OmniLight3D = OmniLight3D.new()
    rim.position = center + Vector3(1.2, 0.65, -1.0).normalized() * radius * 2.4
    rim.omni_range = radius * 6.0
    rim.light_energy = 1.9
    scene_root.add_child(rim)

    var camera: Camera3D = Camera3D.new()
    camera.fov = 38.0
    camera.near = 0.01
    camera.far = maxf(100.0, radius * 20.0)
    scene_root.add_child(camera)
    camera.make_current()

    var base_distance: float = radius / tan(deg_to_rad(camera.fov * 0.5))
    var view_specs: Array[Dictionary] = [
        {
            "name": "hero",
            "direction": Vector3(0.72, 0.34, 1.48),
            "target": center + Vector3(0.0, world_bounds.size.y * 0.015, 0.0),
            "distance_factor": 1.02,
            "min_coverage": 0.045,
        },
        {
            "name": "side",
            "direction": Vector3(0.03, 0.10, 1.0),
            "target": center,
            "distance_factor": 0.96,
            "min_coverage": 0.045,
        },
        {
            "name": "receiver_close",
            "direction": Vector3(0.48, 0.30, 1.42),
            "target": center + Vector3(-world_bounds.size.x * 0.035, world_bounds.size.y * 0.035, 0.0),
            "distance_factor": 0.56,
            "min_coverage": 0.08,
        },
    ]

    var views: Array[Dictionary] = []
    for spec: Dictionary in view_specs:
        var view_name: String = str(spec["name"])
        var direction: Vector3 = (spec["direction"] as Vector3).normalized()
        var target: Vector3 = spec["target"] as Vector3
        var distance: float = base_distance * float(spec["distance_factor"])
        var position: Vector3 = target + direction * distance
        camera.look_at_from_position(position, target, Vector3.UP)
        camera.make_current()
        for _frame: int in range(8):
            await process_frame

        var path: String = "res://godot-view-%s.png" % view_name
        var metrics: Dictionary = capture_metrics(viewport, path)
        var record: Dictionary = {
            "name": view_name,
            "camera": {
                "position": [position.x, position.y, position.z],
                "look_at": [target.x, target.y, target.z],
                "fov": camera.fov,
                "distance": distance,
            },
            "metrics": metrics,
            "minimum_foreground_coverage": float(spec["min_coverage"]),
        }
        views.append(record)
        if str(metrics.get("status", "fail")) != "pass":
            receipt["views"] = views
            fail("View %s failed capture" % view_name, receipt)
            return
        if int(metrics["width"]) != SIZE.x or int(metrics["height"]) != SIZE.y:
            receipt["views"] = views
            fail("View %s dimensions are not 640x640" % view_name, receipt)
            return
        if int(metrics["png_bytes"]) <= 1000:
            receipt["views"] = views
            fail("View %s PNG is unexpectedly small" % view_name, receipt)
            return
        if float(metrics["foreground_coverage"]) < float(spec["min_coverage"]):
            receipt["views"] = views
            fail("View %s coverage too small: %s" % [view_name, metrics["foreground_coverage"]], receipt)
            return
        if float(metrics["luma_range"]) < 0.10:
            receipt["views"] = views
            fail("View %s lacks visible contrast" % view_name, receipt)
            return

    receipt["views"] = views
    receipt["view_count"] = views.size()
    receipt["godot_version"] = Engine.get_version_info()
    receipt["status"] = "pass"
    write_receipt(receipt)
    print("AXM GODOT MULTIVIEW PASS ", JSON.stringify(receipt))
    viewport.queue_free()
    quit(0)
