extends SceneTree

const BODY_PATH := "res://generated/sentinel_hm08_full_body_current_v0_2.gltf"
const ARMOR_PATH := "res://generated/sentinel_armor_v0_1.gltf"
const RECEIPT_PATH := "res://godot-armor-views-receipt.json"
const SIZE := Vector2i(640, 640)
const CLEAR_COLOR := Color(0.022, 0.026, 0.034, 1.0)
const FOREGROUND_DELTA_THRESHOLD := 0.010
const MAX_NEAR_WHITE_FOREGROUND_FRACTION := 0.035

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

func import_gltf(path: String, receipt: Dictionary, label: String) -> Node3D:
    var document := GLTFDocument.new()
    var state := GLTFState.new()
    var err := document.append_from_file(path, state)
    receipt[label + "_append_error"] = err
    if err != OK:
        fail("Godot rejected %s" % label, receipt)
        return null
    var scene := document.generate_scene(state)
    if scene == null or not (scene is Node3D):
        fail("Godot generated no Node3D for %s" % label, receipt)
        return null
    return scene as Node3D

func collect_meshes(node: Node, out: Array[MeshInstance3D]) -> void:
    if node is MeshInstance3D:
        out.append(node as MeshInstance3D)
    for child: Node in node.get_children():
        collect_meshes(child, out)

func transformed_aabb(local_aabb: AABB, transform: Transform3D) -> AABB:
    var p := local_aabb.position
    var s := local_aabb.size
    var corners: Array[Vector3] = [p, p+Vector3(s.x,0,0), p+Vector3(0,s.y,0), p+Vector3(0,0,s.z), p+Vector3(s.x,s.y,0), p+Vector3(s.x,0,s.z), p+Vector3(0,s.y,s.z), p+s]
    var result := AABB(transform * corners[0], Vector3.ZERO)
    for i in range(1, corners.size()):
        result = result.expand(transform * corners[i])
    return result

func aggregate_bounds(root: Node) -> Dictionary:
    var nodes: Array[MeshInstance3D] = []
    collect_meshes(root, nodes)
    var have := false
    var merged := AABB()
    for node in nodes:
        if node.mesh == null:
            continue
        var world := transformed_aabb(node.mesh.get_aabb(), node.global_transform)
        merged = world if not have else merged.merge(world)
        have = true
    return {"have": have, "bounds": merged, "mesh_instances": nodes.size()}

func capture(viewport: SubViewport, path: String) -> Dictionary:
    var image := viewport.get_texture().get_image()
    if image == null or image.is_empty():
        return {"status":"fail","failure":"empty image"}
    var save_error := image.save_png(path)
    if save_error != OK:
        return {"status":"fail","failure":"save failed","save_error":save_error}
    var background := image.get_pixel(2, 2)
    var sampled := 0
    var foreground := 0
    var near_white := 0
    var min_luma := 1.0
    var max_luma := 0.0
    var fg_luma_sum := 0.0
    var min_x := image.get_width()
    var max_x := -1
    var min_y := image.get_height()
    var max_y := -1
    for y in range(0, image.get_height(), 2):
        for x in range(0, image.get_width(), 2):
            var color := image.get_pixel(x, y)
            var delta := absf(color.r-background.r)+absf(color.g-background.g)+absf(color.b-background.b)
            var luma := color.r*0.2126 + color.g*0.7152 + color.b*0.0722
            if delta > FOREGROUND_DELTA_THRESHOLD:
                foreground += 1
                fg_luma_sum += luma
                min_x = mini(min_x, x); max_x = maxi(max_x, x)
                min_y = mini(min_y, y); max_y = maxi(max_y, y)
                if luma >= 0.965:
                    near_white += 1
            min_luma = minf(min_luma, luma)
            max_luma = maxf(max_luma, luma)
            sampled += 1
    var bbox_width := 0.0 if max_x < min_x else float(max_x-min_x+2)/float(image.get_width())
    var bbox_height := 0.0 if max_y < min_y else float(max_y-min_y+2)/float(image.get_height())
    return {
        "status":"pass",
        "path":path,
        "width":image.get_width(),
        "height":image.get_height(),
        "png_bytes":FileAccess.get_file_as_bytes(path).size(),
        "sampled_pixels":sampled,
        "foreground_pixels":foreground,
        "foreground_coverage":float(foreground)/float(maxi(sampled,1)),
        "foreground_bbox_width_fraction":bbox_width,
        "foreground_bbox_height_fraction":bbox_height,
        "near_white_foreground_fraction":float(near_white)/float(maxi(foreground,1)),
        "foreground_luma_mean":fg_luma_sum/float(maxi(foreground,1)),
        "luma_min":min_luma,
        "luma_max":max_luma,
        "luma_range":max_luma-min_luma,
    }

func metrics_green(metrics: Dictionary, minimum_coverage: float) -> bool:
    return metrics.get("status") == "pass" \
        and int(metrics["width"]) == SIZE.x \
        and int(metrics["height"]) == SIZE.y \
        and int(metrics["png_bytes"]) > 1000 \
        and float(metrics["foreground_coverage"]) >= minimum_coverage \
        and float(metrics["luma_range"]) >= 0.08 \
        and float(metrics["near_white_foreground_fraction"]) <= MAX_NEAR_WHITE_FOREGROUND_FRACTION

func _initialize() -> void:
    var receipt: Dictionary = {
        "schema":"game-asset-forge.godot-sentinel-armor-views.v0.1",
        "body_asset":BODY_PATH,
        "armor_asset":ARMOR_PATH,
        "foreground_delta_threshold":FOREGROUND_DELTA_THRESHOLD,
        "exposure_gate":{"max_near_white_foreground_fraction":MAX_NEAR_WHITE_FOREGROUND_FRACTION},
        "truth":"Control and armored character are captured with identical body-derived cameras and lighting. Coverage/bounds deltas prove the armor changed the in-engine silhouette but do not convert aesthetic preference into automatic truth."
    }
    if not FileAccess.file_exists(BODY_PATH) or not FileAccess.file_exists(ARMOR_PATH):
        fail("Body or armor glTF missing", receipt)
        return
    var body := import_gltf(BODY_PATH, receipt, "body")
    if body == null:
        return
    var armor := import_gltf(ARMOR_PATH, receipt, "armor")
    if armor == null:
        body.free(); return

    RenderingServer.set_default_clear_color(CLEAR_COLOR)
    var viewport := SubViewport.new()
    viewport.size = SIZE
    viewport.own_world_3d = true
    viewport.transparent_bg = false
    viewport.render_target_clear_mode = SubViewport.CLEAR_MODE_ALWAYS
    viewport.render_target_update_mode = SubViewport.UPDATE_ALWAYS
    get_root().add_child(viewport)
    var scene_root := Node3D.new()
    viewport.add_child(scene_root)
    scene_root.add_child(body)
    scene_root.add_child(armor)
    await process_frame

    var bounds_state := aggregate_bounds(body)
    if not bool(bounds_state["have"]):
        fail("Body has no bounds", receipt); return
    var body_bounds: AABB = bounds_state["bounds"]
    var center := body_bounds.get_center()
    var radius := maxf(body_bounds.size.length()*0.5, 0.05)
    receipt["body_world_bounds"] = {"position":[body_bounds.position.x,body_bounds.position.y,body_bounds.position.z],"size":[body_bounds.size.x,body_bounds.size.y,body_bounds.size.z]}

    var environment := Environment.new()
    environment.background_mode = Environment.BG_COLOR
    environment.background_color = CLEAR_COLOR
    environment.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
    environment.ambient_light_color = Color(0.50,0.52,0.57,1.0)
    environment.ambient_light_energy = 0.28
    var world_environment := WorldEnvironment.new()
    world_environment.environment = environment
    scene_root.add_child(world_environment)
    var key := DirectionalLight3D.new()
    key.light_energy = 0.52
    key.rotation_degrees = Vector3(-34.0,-28.0,0.0)
    key.shadow_enabled = true
    scene_root.add_child(key)
    var fill := OmniLight3D.new()
    fill.position = center + Vector3(-1.0,0.45,1.0).normalized()*radius*2.1
    fill.omni_range = radius*5.0; fill.light_energy = 0.36
    scene_root.add_child(fill)
    var rim := OmniLight3D.new()
    rim.position = center + Vector3(1.1,0.4,-0.8).normalized()*radius*2.2
    rim.omni_range = radius*5.0; rim.light_energy = 0.30
    scene_root.add_child(rim)
    receipt["lighting"] = {"ambient":environment.ambient_light_energy,"key":key.light_energy,"fill":fill.light_energy,"rim":rim.light_energy}

    var camera := Camera3D.new()
    camera.fov = 34.0; camera.near = 0.01; camera.far = maxf(100.0,radius*20.0)
    scene_root.add_child(camera); camera.make_current()
    var base_distance := radius/tan(deg_to_rad(camera.fov*0.5))
    var target := center + Vector3(0.0,body_bounds.size.y*0.035,body_bounds.size.z*0.055)
    var specs: Array[Dictionary] = [
        {"name":"front","direction":Vector3(0.0,0.02,1.0),"factor":0.92,"min_coverage":0.12},
        {"name":"three_quarter","direction":Vector3(0.62,0.05,1.0),"factor":0.96,"min_coverage":0.10},
        {"name":"profile","direction":Vector3(1.0,0.02,0.03),"factor":0.90,"min_coverage":0.09},
    ]
    var views: Array[Dictionary] = []
    var coverage_delta_sum := 0.0
    for spec in specs:
        var name := str(spec["name"])
        var direction: Vector3 = (spec["direction"] as Vector3).normalized()
        var distance := base_distance*float(spec["factor"])
        var position := target + direction*distance
        camera.look_at_from_position(position,target,Vector3.UP)
        camera.make_current()

        armor.visible = false
        for _frame in range(6): await process_frame
        var control_path := "res://control-%s.png" % name
        var control := capture(viewport, control_path)

        armor.visible = true
        for _frame in range(8): await process_frame
        var armored_path := "res://armored-%s.png" % name
        var armored := capture(viewport, armored_path)

        var coverage_delta := float(armored["foreground_coverage"]) - float(control["foreground_coverage"])
        coverage_delta_sum += coverage_delta
        var record := {
            "name":name,
            "camera":{"position":[position.x,position.y,position.z],"look_at":[target.x,target.y,target.z],"fov":camera.fov,"distance":distance},
            "minimum_foreground_coverage":float(spec["min_coverage"]),
            "control":control,
            "armored":armored,
            "coverage_delta":coverage_delta,
            "bbox_width_delta":float(armored["foreground_bbox_width_fraction"])-float(control["foreground_bbox_width_fraction"]),
        }
        views.append(record)
        if not metrics_green(control,float(spec["min_coverage"])) or not metrics_green(armored,float(spec["min_coverage"])):
            receipt["views"] = views
            fail("Armor view %s failed technical framing/exposure gate" % name, receipt)
            return
    receipt["views"] = views
    receipt["coverage_delta_sum"] = coverage_delta_sum
    if coverage_delta_sum <= 0.002:
        fail("Armor overlay produced too little measurable whole-character coverage change", receipt)
        return
    receipt["status"] = "pass"
    receipt["godot_version"] = Engine.get_version_info()
    write_receipt(receipt)
    print("GAME ASSET FORGE GODOT ARMOR VIEWS PASS ", JSON.stringify(receipt))
    viewport.queue_free()
    quit(0)
