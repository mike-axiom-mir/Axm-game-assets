extends SceneTree

const ASSET_PATH := "res://generated_blender/Kettlejack_game_character.glb"
const RECEIPT_PATH := "res://godot-kettlejack-blender-render-receipt.json"
const SIZE := Vector2i(640, 640)
const CLEAR := Color(0.045, 0.050, 0.062, 1.0)

func write_receipt(data: Dictionary) -> void:
    var file := FileAccess.open(RECEIPT_PATH, FileAccess.WRITE)
    if file != null:
        file.store_string(JSON.stringify(data, "  ") + "\n")
        file.close()

func fail(message: String, data: Dictionary) -> void:
    data["status"] = "fail"
    data["failure"] = message
    data["godot_version"] = Engine.get_version_info()
    write_receipt(data)
    push_error(message)
    quit(1)

func collect(node: Node, meshes: Array[MeshInstance3D], players: Array[AnimationPlayer]) -> void:
    if node is MeshInstance3D:
        meshes.append(node as MeshInstance3D)
    if node is AnimationPlayer:
        players.append(node as AnimationPlayer)
    for child: Node in node.get_children():
        collect(child, meshes, players)

func transformed_aabb(local_aabb: AABB, transform: Transform3D) -> AABB:
    var p := local_aabb.position
    var s := local_aabb.size
    var corners: Array[Vector3] = [
        p, p + Vector3(s.x, 0, 0), p + Vector3(0, s.y, 0), p + Vector3(0, 0, s.z),
        p + Vector3(s.x, s.y, 0), p + Vector3(s.x, 0, s.z), p + Vector3(0, s.y, s.z), p + s,
    ]
    var out := AABB(transform * corners[0], Vector3.ZERO)
    for i in range(1, corners.size()):
        out = out.expand(transform * corners[i])
    return out

func aggregate_bounds(meshes: Array[MeshInstance3D]) -> AABB:
    var have := false
    var out := AABB()
    for mesh in meshes:
        if mesh.mesh == null:
            continue
        var world := transformed_aabb(mesh.mesh.get_aabb(), mesh.global_transform)
        out = world if not have else out.merge(world)
        have = true
    return out if have else AABB(Vector3.ZERO, Vector3.ZERO)

func image_metrics(image: Image) -> Dictionary:
    var bg := image.get_pixel(2, 2)
    var sampled := 0
    var foreground := 0
    var luma_min := 1.0
    var luma_max := 0.0
    for y in range(0, image.get_height(), 2):
        for x in range(0, image.get_width(), 2):
            var c := image.get_pixel(x, y)
            var delta := absf(c.r-bg.r) + absf(c.g-bg.g) + absf(c.b-bg.b)
            var luma := c.r*.2126 + c.g*.7152 + c.b*.0722
            if delta > .012:
                foreground += 1
            luma_min = minf(luma_min, luma)
            luma_max = maxf(luma_max, luma)
            sampled += 1
    return {
        "foreground_coverage": float(foreground) / float(maxi(sampled, 1)),
        "luma_range": luma_max - luma_min,
        "sampled_pixels": sampled,
    }

func capture(viewport: SubViewport, path: String) -> Dictionary:
    var image := viewport.get_texture().get_image()
    if image == null or image.is_empty():
        return {"status": "fail", "failure": "empty image"}
    var error := image.save_png(path)
    if error != OK:
        return {"status": "fail", "failure": "save failed", "error": error}
    return {
        "status": "pass",
        "path": path,
        "width": image.get_width(),
        "height": image.get_height(),
        "png_bytes": FileAccess.get_file_as_bytes(path).size(),
        "metrics": image_metrics(image),
    }

func resolve_clip(player: AnimationPlayer, clip: String) -> StringName:
    if player.has_animation(clip):
        return StringName(clip)
    for library_name in player.get_animation_library_list():
        var library := player.get_animation_library(library_name)
        if library != null and library.has_animation(clip):
            if String(library_name).is_empty():
                return StringName(clip)
            return StringName("%s/%s" % [library_name, clip])
    return StringName()

func set_pose(player: AnimationPlayer, clip: String, fraction: float) -> Dictionary:
    var key := resolve_clip(player, clip)
    if String(key).is_empty():
        return {"status": "fail", "failure": "missing animation %s" % clip}
    var animation := player.get_animation(key)
    if animation == null:
        return {"status": "fail", "failure": "could not resolve animation %s" % clip}
    var time := clampf(fraction, 0.0, 1.0) * animation.length
    player.play(key)
    player.seek(time, true)
    player.advance(0.0)
    return {"status": "pass", "animation_key": String(key), "time": time, "length": animation.length}

func _initialize() -> void:
    var receipt: Dictionary = {
        "schema": "axm.game-assets.godot-kettlejack-blender-render/v0.1",
        "asset": ASSET_PATH,
        "truth": "Retained pixels from the exact exported GLB played in Godot 4.7.2. This proves downstream engine pose/camera/render evidence; it does not automatically approve aesthetics, concept fidelity, deformation quality, performance or CANON.",
    }
    if not FileAccess.file_exists(ASSET_PATH):
        fail("Blender-foundry Kettlejack missing", receipt)
        return

    RenderingServer.set_default_clear_color(CLEAR)
    var document := GLTFDocument.new()
    var state := GLTFState.new()
    var parse_error := document.append_from_file(ASSET_PATH, state)
    if parse_error != OK:
        fail("Godot rejected Blender-foundry Kettlejack", receipt)
        return
    var imported := document.generate_scene(state)
    if imported == null:
        fail("Godot generated no scene", receipt)
        return

    var viewport := SubViewport.new()
    viewport.size = SIZE
    viewport.own_world_3d = true
    viewport.transparent_bg = false
    viewport.render_target_clear_mode = SubViewport.CLEAR_MODE_ALWAYS
    viewport.render_target_update_mode = SubViewport.UPDATE_ALWAYS
    get_root().add_child(viewport)
    var scene_root := Node3D.new()
    viewport.add_child(scene_root)
    scene_root.add_child(imported)

    var meshes: Array[MeshInstance3D] = []
    var players: Array[AnimationPlayer] = []
    collect(imported, meshes, players)
    if meshes.is_empty() or players.is_empty():
        fail("review requires mesh and animation player", receipt)
        return
    var player := players[0]

    var env := Environment.new()
    env.background_mode = Environment.BG_COLOR
    env.background_color = CLEAR
    env.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
    env.ambient_light_color = Color(.58, .60, .66, 1)
    env.ambient_light_energy = .40
    var world_env := WorldEnvironment.new()
    world_env.environment = env
    scene_root.add_child(world_env)
    var key := DirectionalLight3D.new()
    key.light_energy = .84
    key.rotation_degrees = Vector3(-36, -30, 0)
    key.shadow_enabled = true
    scene_root.add_child(key)
    var fill := OmniLight3D.new()
    fill.light_energy = .45
    scene_root.add_child(fill)
    var rim := OmniLight3D.new()
    rim.light_energy = .38
    scene_root.add_child(rim)

    var plane_mesh := PlaneMesh.new()
    plane_mesh.size = Vector2(4.0, 4.0)
    var floor := MeshInstance3D.new()
    floor.mesh = plane_mesh
    floor.position = Vector3(0, -.004, 0)
    var floor_mat := StandardMaterial3D.new()
    floor_mat.albedo_color = Color(.14, .15, .18, 1)
    floor_mat.roughness = .92
    floor.material_override = floor_mat
    scene_root.add_child(floor)

    var camera := Camera3D.new()
    camera.fov = 32.0
    camera.near = .01
    camera.far = 100.0
    scene_root.add_child(camera)
    camera.make_current()

    var specs: Array[Dictionary] = [
        {"name":"front", "clip":"Idle", "fraction":0.0, "direction":Vector3(0,.03,1), "factor":.90},
        {"name":"three_quarter", "clip":"Idle", "fraction":0.0, "direction":Vector3(.62,.04,1), "factor":.94},
        {"name":"side", "clip":"Idle", "fraction":0.0, "direction":Vector3(1,.03,.03), "factor":.92},
        {"name":"back", "clip":"Idle", "fraction":0.0, "direction":Vector3(0,.03,-1), "factor":.92},
        {"name":"idle", "clip":"Idle", "fraction":.50, "direction":Vector3(.50,.04,1), "factor":.92},
        {"name":"run", "clip":"Run", "fraction":.25, "direction":Vector3(.50,.04,1), "factor":.96},
        {"name":"jump", "clip":"Jump", "fraction":.50, "direction":Vector3(.50,.04,1), "factor":1.00},
        {"name":"wrench_swing", "clip":"Wrench_Swing", "fraction":.55, "direction":Vector3(.50,.04,1), "factor":1.02},
        {"name":"victory", "clip":"Victory", "fraction":.50, "direction":Vector3(.50,.04,1), "factor":.98},
    ]

    var records: Array[Dictionary] = []
    for spec in specs:
        var pose := set_pose(player, str(spec["clip"]), float(spec["fraction"]))
        if pose.get("status") != "pass":
            fail(str(pose.get("failure", "pose failure")), receipt)
            return
        for _i in range(6):
            await process_frame
        var bounds := aggregate_bounds(meshes)
        if bounds.size.length() <= .001:
            fail("invalid rendered bounds", receipt)
            return
        var center := bounds.get_center()
        var radius := maxf(bounds.size.length()*.5, .05)
        fill.position = center + Vector3(-1,.5,1).normalized()*radius*2.2
        fill.omni_range = radius*5
        rim.position = center + Vector3(1,.6,-1).normalized()*radius*2.4
        rim.omni_range = radius*5
        var target := center + Vector3(0, bounds.size.y*.03, bounds.size.z*.03)
        var distance := radius / tan(deg_to_rad(camera.fov*.5)) * float(spec["factor"])
        var direction: Vector3 = (spec["direction"] as Vector3).normalized()
        var position := target + direction*distance
        camera.look_at_from_position(position, target, Vector3.UP)
        for _i in range(8):
            await process_frame
        var path := "res://godot-kettlejack-blender-render-%s.png" % str(spec["name"])
        var captured := capture(viewport, path)
        if captured.get("status") != "pass" or int(captured.get("png_bytes", 0)) < 1500:
            receipt["captures"] = records
            fail("capture failed: %s" % str(spec["name"]), receipt)
            return
        var metrics: Dictionary = captured["metrics"]
        if float(metrics["foreground_coverage"]) < .05 or float(metrics["luma_range"]) < .07:
            receipt["captures"] = records
            fail("technical framing failed: %s" % str(spec["name"]), receipt)
            return
        records.append({
            "name": spec["name"],
            "clip": spec["clip"],
            "pose": pose,
            "capture": captured,
            "camera": {"position":[position.x,position.y,position.z], "target":[target.x,target.y,target.z], "fov":camera.fov},
        })

    receipt["captures"] = records
    receipt["capture_count"] = records.size()
    receipt["godot_version"] = Engine.get_version_info()
    receipt["status"] = "pass"
    write_receipt(receipt)
    print("AXM GODOT KETTLEJACK BLENDER RENDER PASS ", JSON.stringify(receipt))
    viewport.queue_free()
    quit(0)
