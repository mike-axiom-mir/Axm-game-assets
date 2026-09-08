extends SceneTree

const ASSET_PATH: String = "res://generated/sentinel_hm08_face_candidate_v0_1.gltf"
const RECEIPT_PATH: String = "res://godot-full-body-views-receipt.json"
const SIZE: Vector2i = Vector2i(640, 640)
const CLEAR_COLOR: Color = Color(0.022, 0.026, 0.034, 1.0)
const FOREGROUND_DELTA_THRESHOLD: float = 0.010
const MAX_NEAR_WHITE_FOREGROUND_FRACTION: float = 0.035

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

func transformed_aabb(local_aabb: AABB, transform: Transform3D) -> AABB:
    var p: Vector3 = local_aabb.position
    var s: Vector3 = local_aabb.size
    var corners: Array[Vector3] = [p, p+Vector3(s.x,0,0), p+Vector3(0,s.y,0), p+Vector3(0,0,s.z), p+Vector3(s.x,s.y,0), p+Vector3(s.x,0,s.z), p+Vector3(0,s.y,s.z), p+s]
    var result: AABB = AABB(transform * corners[0], Vector3.ZERO)
    for i: int in range(1, corners.size()):
        result = result.expand(transform * corners[i])
    return result

func aggregate_bounds(root: Node) -> Dictionary:
    var nodes: Array[MeshInstance3D] = []
    collect_meshes(root, nodes)
    var have: bool = false
    var merged: AABB = AABB()
    for node: MeshInstance3D in nodes:
        if node.mesh == null:
            continue
        var world: AABB = transformed_aabb(node.mesh.get_aabb(), node.global_transform)
        merged = world if not have else merged.merge(world)
        have = true
    return {"have": have, "bounds": merged, "mesh_instances": nodes.size()}

func capture(viewport: SubViewport, path: String) -> Dictionary:
    var image: Image = viewport.get_texture().get_image()
    if image == null or image.is_empty():
        return {"status":"fail","failure":"empty image"}
    var save_error: int = image.save_png(path)
    if save_error != OK:
        return {"status":"fail","failure":"save failed","save_error":save_error}
    var background: Color = image.get_pixel(2, 2)
    var sampled: int = 0
    var foreground: int = 0
    var near_white_foreground: int = 0
    var min_luma: float = 1.0
    var max_luma: float = 0.0
    var luma_sum: float = 0.0
    var foreground_luma_sum: float = 0.0
    for y: int in range(0, image.get_height(), 2):
        for x: int in range(0, image.get_width(), 2):
            var color: Color = image.get_pixel(x, y)
            var delta: float = absf(color.r-background.r)+absf(color.g-background.g)+absf(color.b-background.b)
            var luma: float = color.r*0.2126 + color.g*0.7152 + color.b*0.0722
            if delta > FOREGROUND_DELTA_THRESHOLD:
                foreground += 1
                foreground_luma_sum += luma
                if luma >= 0.965:
                    near_white_foreground += 1
            min_luma = minf(min_luma, luma)
            max_luma = maxf(max_luma, luma)
            luma_sum += luma
            sampled += 1
    return {
        "status":"pass",
        "path":path,
        "width":image.get_width(),
        "height":image.get_height(),
        "png_bytes":FileAccess.get_file_as_bytes(path).size(),
        "sampled_pixels":sampled,
        "foreground_pixels":foreground,
        "foreground_coverage":float(foreground)/float(maxi(sampled,1)),
        "foreground_delta_threshold":FOREGROUND_DELTA_THRESHOLD,
        "near_white_foreground_pixels":near_white_foreground,
        "near_white_foreground_fraction":float(near_white_foreground)/float(maxi(foreground,1)),
        "foreground_luma_mean":foreground_luma_sum/float(maxi(foreground,1)),
        "luma_min":min_luma,
        "luma_max":max_luma,
        "luma_mean":luma_sum/float(maxi(sampled,1)),
        "luma_range":max_luma-min_luma,
        "background_sample":[background.r,background.g,background.b,background.a],
    }

func _initialize() -> void:
    var receipt: Dictionary = {
        "schema":"axm.game-assets.godot-full-body-views.v0.2",
        "asset":ASSET_PATH,
        "foreground_gate":{
            "known_clear_color":[CLEAR_COLOR.r,CLEAR_COLOR.g,CLEAR_COLOR.b,CLEAR_COLOR.a],
            "delta_threshold":FOREGROUND_DELTA_THRESHOLD,
            "reason":"Whole-body evidence must detect dark garment pixels against the deterministic dark clear color without reducing the silhouette-size acceptance gate."
        },
        "exposure_gate":{"max_near_white_foreground_fraction":MAX_NEAR_WHITE_FOREGROUND_FRACTION},
        "truth":"Real Godot whole-body framing and exposure facts. The foreground detector is deliberately sensitive to dark clothing against the known deterministic background; front/three-quarter/profile size gates and the near-white exposure cap remain unchanged. No aesthetic score, body-quality promotion, or identity claim is encoded."
    }
    if not FileAccess.file_exists(ASSET_PATH):
        fail("Full-body glTF missing", receipt)
        return

    RenderingServer.set_default_clear_color(CLEAR_COLOR)
    var document: GLTFDocument = GLTFDocument.new()
    var state: GLTFState = GLTFState.new()
    var parse_error: int = document.append_from_file(ASSET_PATH, state)
    receipt["append_from_file_error"] = parse_error
    if parse_error != OK:
        fail("Godot rejected full-body asset", receipt)
        return
    var imported: Node = document.generate_scene(state)
    if imported == null:
        fail("Godot generated no full-body scene", receipt)
        return

    var viewport: SubViewport = SubViewport.new()
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

    var bounds_state: Dictionary = aggregate_bounds(imported)
    if not bool(bounds_state["have"]):
        fail("Full-body scene has no mesh bounds", receipt)
        return
    var bounds: AABB = bounds_state["bounds"]
    var center: Vector3 = bounds.get_center()
    var radius: float = maxf(bounds.size.length()*0.5, 0.05)
    receipt["world_bounds"] = {"position":[bounds.position.x,bounds.position.y,bounds.position.z],"size":[bounds.size.x,bounds.size.y,bounds.size.z],"center":[center.x,center.y,center.z],"radius":radius}

    var environment: Environment = Environment.new()
    environment.background_mode = Environment.BG_COLOR
    environment.background_color = CLEAR_COLOR
    environment.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
    environment.ambient_light_color = Color(0.50, 0.52, 0.57, 1.0)
    environment.ambient_light_energy = 0.28
    var world_environment: WorldEnvironment = WorldEnvironment.new()
    world_environment.environment = environment
    scene_root.add_child(world_environment)

    var key: DirectionalLight3D = DirectionalLight3D.new()
    key.light_energy = 0.52
    key.rotation_degrees = Vector3(-34.0, -28.0, 0.0)
    key.shadow_enabled = true
    scene_root.add_child(key)
    var fill: OmniLight3D = OmniLight3D.new()
    fill.position = center + Vector3(-1.0, 0.45, 1.0).normalized()*radius*2.1
    fill.omni_range = radius*5.0
    fill.light_energy = 0.36
    scene_root.add_child(fill)
    var rim: OmniLight3D = OmniLight3D.new()
    rim.position = center + Vector3(1.1, 0.4, -0.8).normalized()*radius*2.2
    rim.omni_range = radius*5.0
    rim.light_energy = 0.30
    scene_root.add_child(rim)
    receipt["lighting"] = {
        "ambient_energy":environment.ambient_light_energy,
        "key_energy":key.light_energy,
        "fill_energy":fill.light_energy,
        "rim_energy":rim.light_energy,
    }

    var camera: Camera3D = Camera3D.new()
    camera.fov = 34.0
    camera.near = 0.01
    camera.far = maxf(100.0, radius*20.0)
    scene_root.add_child(camera)
    camera.make_current()
    var base_distance: float = radius/tan(deg_to_rad(camera.fov*0.5))
    var body_target: Vector3 = center + Vector3(0.0, bounds.size.y*0.035, bounds.size.z*0.055)
    var specs: Array[Dictionary] = [
        {"name":"front","direction":Vector3(0.0,0.02,1.0),"factor":0.92,"min_coverage":0.12},
        {"name":"three_quarter","direction":Vector3(0.62,0.05,1.0),"factor":0.96,"min_coverage":0.10},
        {"name":"profile","direction":Vector3(1.0,0.02,0.03),"factor":0.90,"min_coverage":0.09},
    ]
    var views: Array[Dictionary] = []
    for spec: Dictionary in specs:
        var name: String = str(spec["name"])
        var direction: Vector3 = (spec["direction"] as Vector3).normalized()
        var distance: float = base_distance*float(spec["factor"])
        var position: Vector3 = body_target + direction*distance
        camera.look_at_from_position(position, body_target, Vector3.UP)
        camera.make_current()
        for _frame: int in range(8):
            await process_frame
        var path: String = "res://godot-full-body-%s.png" % name
        var metrics: Dictionary = capture(viewport, path)
        var record: Dictionary = {"name":name,"camera":{"position":[position.x,position.y,position.z],"look_at":[body_target.x,body_target.y,body_target.z],"fov":camera.fov,"distance":distance},"metrics":metrics,"minimum_foreground_coverage":float(spec["min_coverage"]),"maximum_near_white_foreground_fraction":MAX_NEAR_WHITE_FOREGROUND_FRACTION}
        views.append(record)
        if metrics.get("status") != "pass" or int(metrics["width"]) != SIZE.x or int(metrics["height"]) != SIZE.y or int(metrics["png_bytes"]) <= 1000 or float(metrics["foreground_coverage"]) < float(spec["min_coverage"]) or float(metrics["luma_range"]) < 0.08 or float(metrics["near_white_foreground_fraction"]) > MAX_NEAR_WHITE_FOREGROUND_FRACTION:
            receipt["views"] = views
            fail("Full-body view %s failed technical capture/exposure gate" % name, receipt)
            return

    receipt["views"] = views
    receipt["view_count"] = views.size()
    receipt["godot_version"] = Engine.get_version_info()
    receipt["status"] = "pass"
    write_receipt(receipt)
    print("GAME ASSET FORGE GODOT FULL BODY VIEWS PASS ", JSON.stringify(receipt))
    viewport.queue_free()
    quit(0)
