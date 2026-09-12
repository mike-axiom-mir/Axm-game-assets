extends SceneTree

const ASSET_PATH := "res://generated/kettlejack_game_character_v0_2.gltf"
const RECEIPT_PATH := "res://godot-kettlejack-review-receipt.json"
const SIZE := Vector2i(640, 640)
const CLEAR_COLOR := Color(0.018, 0.022, 0.030, 1.0)

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
        p, p+Vector3(s.x,0,0), p+Vector3(0,s.y,0), p+Vector3(0,0,s.z),
        p+Vector3(s.x,s.y,0), p+Vector3(s.x,0,s.z), p+Vector3(0,s.y,s.z), p+s
    ]
    var result := AABB(transform * corners[0], Vector3.ZERO)
    for i in range(1, corners.size()):
        result = result.expand(transform * corners[i])
    return result

func aggregate_bounds(root: Node) -> AABB:
    var meshes: Array[MeshInstance3D] = []
    var players: Array[AnimationPlayer] = []
    collect(root, meshes, players)
    var have := false
    var merged := AABB()
    for node in meshes:
        if node.mesh == null:
            continue
        var world := transformed_aabb(node.mesh.get_aabb(), node.global_transform)
        merged = world if not have else merged.merge(world)
        have = true
    if not have:
        return AABB(Vector3.ZERO, Vector3.ZERO)
    return merged

func image_metrics(image: Image) -> Dictionary:
    var bg := image.get_pixel(2,2)
    var sampled := 0
    var foreground := 0
    var luma_min := 1.0
    var luma_max := 0.0
    for y in range(0,image.get_height(),2):
        for x in range(0,image.get_width(),2):
            var c := image.get_pixel(x,y)
            var delta := absf(c.r-bg.r)+absf(c.g-bg.g)+absf(c.b-bg.b)
            var luma := c.r*.2126+c.g*.7152+c.b*.0722
            if delta > .012:
                foreground += 1
            luma_min=minf(luma_min,luma)
            luma_max=maxf(luma_max,luma)
            sampled += 1
    return {
        "foreground_coverage":float(foreground)/float(maxi(sampled,1)),
        "luma_range":luma_max-luma_min,
        "sampled_pixels":sampled,
    }

func capture(viewport: SubViewport, path: String) -> Dictionary:
    var image := viewport.get_texture().get_image()
    if image == null or image.is_empty():
        return {"status":"fail","failure":"empty image"}
    var err := image.save_png(path)
    if err != OK:
        return {"status":"fail","failure":"save failed","error":err}
    var metrics := image_metrics(image)
    return {
        "status":"pass","path":path,"width":image.get_width(),"height":image.get_height(),
        "png_bytes":FileAccess.get_file_as_bytes(path).size(),"metrics":metrics
    }

func set_pose(players: Array[AnimationPlayer], clip: String, time: float) -> bool:
    if players.is_empty():
        return false
    var player := players[0]
    if not player.has_animation(clip):
        return false
    player.play(clip)
    player.seek(time, true)
    player.advance(0.0)
    return true

func _initialize() -> void:
    var receipt: Dictionary = {
        "schema":"axm.game-assets.godot-kettlejack-review/v0.1",
        "asset":ASSET_PATH,
        "truth":"Exact Godot render captures for visual review. These prove pixels were rendered from this imported character/clip/camera state; they do not automatically judge aesthetic quality, concept fidelity, deformation quality, performance or CANON."
    }
    if not FileAccess.file_exists(ASSET_PATH):
        fail("Kettlejack v0.2 glTF missing",receipt)
        return

    RenderingServer.set_default_clear_color(CLEAR_COLOR)
    var document := GLTFDocument.new()
    var state := GLTFState.new()
    var parse_error := document.append_from_file(ASSET_PATH,state)
    receipt["append_from_file_error"] = parse_error
    if parse_error != OK:
        fail("Godot rejected Kettlejack v0.2",receipt)
        return
    var imported := document.generate_scene(state)
    if imported == null:
        fail("Godot generated no Kettlejack scene",receipt)
        return

    var viewport := SubViewport.new()
    viewport.size=SIZE
    viewport.own_world_3d=true
    viewport.transparent_bg=false
    viewport.render_target_clear_mode=SubViewport.CLEAR_MODE_ALWAYS
    viewport.render_target_update_mode=SubViewport.UPDATE_ALWAYS
    get_root().add_child(viewport)
    var scene_root := Node3D.new()
    viewport.add_child(scene_root)
    scene_root.add_child(imported)

    var meshes: Array[MeshInstance3D] = []
    var players: Array[AnimationPlayer] = []
    collect(imported,meshes,players)
    if meshes.is_empty() or players.is_empty():
        fail("Kettlejack review requires mesh and animation player",receipt)
        return

    var env := Environment.new()
    env.background_mode=Environment.BG_COLOR
    env.background_color=CLEAR_COLOR
    env.ambient_light_source=Environment.AMBIENT_SOURCE_COLOR
    env.ambient_light_color=Color(.55,.57,.62,1)
    env.ambient_light_energy=.38
    var world_env := WorldEnvironment.new()
    world_env.environment=env
    scene_root.add_child(world_env)
    var key := DirectionalLight3D.new()
    key.light_energy=.72
    key.rotation_degrees=Vector3(-34,-28,0)
    key.shadow_enabled=true
    scene_root.add_child(key)
    var fill := OmniLight3D.new()
    fill.light_energy=.46
    scene_root.add_child(fill)
    var rim := OmniLight3D.new()
    rim.light_energy=.34
    scene_root.add_child(rim)

    var camera := Camera3D.new()
    camera.fov=32.0
    camera.near=.01
    camera.far=100.0
    scene_root.add_child(camera)
    camera.make_current()

    var records: Array[Dictionary] = []
    var specs: Array[Dictionary] = [
        {"name":"front","clip":"idle","time":0.0,"direction":Vector3(0,.03,1),"factor":.86},
        {"name":"three_quarter","clip":"idle","time":0.0,"direction":Vector3(.62,.04,1),"factor":.90},
        {"name":"side","clip":"idle","time":0.0,"direction":Vector3(1,.03,.03),"factor":.88},
        {"name":"back","clip":"idle","time":0.0,"direction":Vector3(0,.03,-1),"factor":.88},
        {"name":"idle","clip":"idle","time":.8,"direction":Vector3(.50,.04,1),"factor":.88},
        {"name":"run","clip":"run","time":.20,"direction":Vector3(.50,.04,1),"factor":.90},
        {"name":"jump","clip":"jump","time":.24,"direction":Vector3(.50,.04,1),"factor":.90},
        {"name":"wrench_swing","clip":"wrench_swing","time":.38,"direction":Vector3(.50,.04,1),"factor":.94},
        {"name":"victory","clip":"victory","time":.35,"direction":Vector3(.50,.04,1),"factor":.92},
    ]

    for spec in specs:
        if not set_pose(players,str(spec["clip"]),float(spec["time"])):
            fail("Missing review clip %s" % str(spec["clip"]),receipt)
            return
        for _i in range(5):
            await process_frame
        var b := aggregate_bounds(imported)
        if b.size.length() <= .001:
            fail("Kettlejack review bounds invalid",receipt)
            return
        var center := b.get_center()
        var radius := maxf(b.size.length()*.5,.05)
        fill.position=center+Vector3(-1,.5,1).normalized()*radius*2.2
        fill.omni_range=radius*5
        rim.position=center+Vector3(1,.6,-1).normalized()*radius*2.4
        rim.omni_range=radius*5
        var target := center+Vector3(0,b.size.y*.03,b.size.z*.03)
        var base_distance := radius/tan(deg_to_rad(camera.fov*.5))
        var direction: Vector3=(spec["direction"] as Vector3).normalized()
        var position := target+direction*base_distance*float(spec["factor"])
        camera.look_at_from_position(position,target,Vector3.UP)
        for _i in range(7):
            await process_frame
        var path := "res://godot-kettlejack-review-%s.png" % str(spec["name"])
        var capture_state := capture(viewport,path)
        if capture_state.get("status")!="pass" or int(capture_state.get("png_bytes",0))<1200:
            receipt["captures"]=records
            fail("Kettlejack review capture failed: %s" % str(spec["name"]),receipt)
            return
        var metrics: Dictionary=capture_state["metrics"]
        if float(metrics["foreground_coverage"])<.06 or float(metrics["luma_range"])<.08:
            receipt["captures"]=records
            fail("Kettlejack review technical framing failed: %s" % str(spec["name"]),receipt)
            return
        records.append({
            "name":spec["name"],"clip":spec["clip"],"time":spec["time"],"path":path,
            "camera":{"position":[position.x,position.y,position.z],"look_at":[target.x,target.y,target.z],"fov":camera.fov},
            "bounds":{"position":[b.position.x,b.position.y,b.position.z],"size":[b.size.x,b.size.y,b.size.z]},
            "capture":capture_state,
        })

    receipt["captures"]=records
    receipt["capture_count"]=records.size()
    receipt["godot_version"]=Engine.get_version_info()
    receipt["status"]="pass"
    write_receipt(receipt)
    print("AXM KETTLEJACK VISUAL REVIEW CAPTURE PASS ",JSON.stringify(receipt))
    viewport.queue_free()
    quit(0)
