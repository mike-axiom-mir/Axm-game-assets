extends SceneTree

const ASSET_PATH := "res://generated/kettlejack_game_character_v0_3.gltf"
const RECEIPT_PATH := "res://godot-kettlejack-v3-review-receipt.json"
const SIZE := Vector2i(640,640)
const CLEAR := Color(0.018,0.022,0.030,1.0)

func write_receipt(data: Dictionary) -> void:
    var f:=FileAccess.open(RECEIPT_PATH,FileAccess.WRITE)
    if f!=null:
        f.store_string(JSON.stringify(data,"  ")+"\n")
        f.close()

func fail(message:String,data:Dictionary)->void:
    data["status"]="fail"
    data["failure"]=message
    data["godot_version"]=Engine.get_version_info()
    write_receipt(data)
    push_error(message)
    quit(1)

func collect(node:Node,meshes:Array[MeshInstance3D],players:Array[AnimationPlayer])->void:
    if node is MeshInstance3D:
        meshes.append(node as MeshInstance3D)
    if node is AnimationPlayer:
        players.append(node as AnimationPlayer)
    for child:Node in node.get_children():
        collect(child,meshes,players)

func transformed_aabb(aabb:AABB,t:Transform3D)->AABB:
    var p:=aabb.position
    var s:=aabb.size
    var c:Array[Vector3]=[p,p+Vector3(s.x,0,0),p+Vector3(0,s.y,0),p+Vector3(0,0,s.z),p+Vector3(s.x,s.y,0),p+Vector3(s.x,0,s.z),p+Vector3(0,s.y,s.z),p+s]
    var out:=AABB(t*c[0],Vector3.ZERO)
    for i in range(1,c.size()): out=out.expand(t*c[i])
    return out

func bounds_of(root:Node)->AABB:
    var meshes:Array[MeshInstance3D]=[]
    var players:Array[AnimationPlayer]=[]
    collect(root,meshes,players)
    var have:=false
    var out:=AABB()
    for m in meshes:
        if m.mesh==null: continue
        var world:=transformed_aabb(m.mesh.get_aabb(),m.global_transform)
        out=world if not have else out.merge(world)
        have=true
    return out if have else AABB(Vector3.ZERO,Vector3.ZERO)

func metrics(image:Image)->Dictionary:
    var bg:=image.get_pixel(2,2)
    var sample:=0
    var fg:=0
    var lo:=1.0
    var hi:=0.0
    for y in range(0,image.get_height(),2):
        for x in range(0,image.get_width(),2):
            var c:=image.get_pixel(x,y)
            var d:=absf(c.r-bg.r)+absf(c.g-bg.g)+absf(c.b-bg.b)
            var l:=c.r*.2126+c.g*.7152+c.b*.0722
            if d>.012: fg+=1
            lo=minf(lo,l);hi=maxf(hi,l);sample+=1
    return {"foreground_coverage":float(fg)/float(maxi(sample,1)),"luma_range":hi-lo}

func capture(viewport:SubViewport,path:String)->Dictionary:
    var image:=viewport.get_texture().get_image()
    if image==null or image.is_empty(): return {"status":"fail"}
    var err:=image.save_png(path)
    if err!=OK: return {"status":"fail","error":err}
    return {"status":"pass","path":path,"png_bytes":FileAccess.get_file_as_bytes(path).size(),"metrics":metrics(image)}

func pose(players:Array[AnimationPlayer],clip:String,time:float)->bool:
    if players.is_empty(): return false
    var p:=players[0]
    if not p.has_animation(clip): return false
    p.play(clip)
    p.seek(time,true)
    p.advance(0.0)
    return true

func _initialize()->void:
    var receipt:Dictionary={
        "schema":"axm.game-assets.godot-kettlejack-v3-review/v0.1",
        "asset":ASSET_PATH,
        "truth":"Exact Godot render captures for v0.3 visual review. Pixel existence/framing are proven; aesthetic quality, concept fidelity, deformation quality, performance and CANON remain external judgments."
    }
    if not FileAccess.file_exists(ASSET_PATH): fail("v0.3 asset missing",receipt);return
    RenderingServer.set_default_clear_color(CLEAR)
    var doc:=GLTFDocument.new();var state:=GLTFState.new()
    var err:=doc.append_from_file(ASSET_PATH,state)
    if err!=OK: fail("Godot rejected v0.3 glTF",receipt);return
    var imported:=doc.generate_scene(state)
    if imported==null: fail("Godot generated no scene",receipt);return

    var viewport:=SubViewport.new();viewport.size=SIZE;viewport.own_world_3d=true;viewport.transparent_bg=false;viewport.render_target_clear_mode=SubViewport.CLEAR_MODE_ALWAYS;viewport.render_target_update_mode=SubViewport.UPDATE_ALWAYS
    get_root().add_child(viewport)
    var root:=Node3D.new();viewport.add_child(root);root.add_child(imported)
    var meshes:Array[MeshInstance3D]=[];var players:Array[AnimationPlayer]=[];collect(imported,meshes,players)
    if meshes.is_empty() or players.is_empty(): fail("review needs mesh and animation player",receipt);return

    var env:=Environment.new();env.background_mode=Environment.BG_COLOR;env.background_color=CLEAR;env.ambient_light_source=Environment.AMBIENT_SOURCE_COLOR;env.ambient_light_color=Color(.56,.58,.64,1);env.ambient_light_energy=.42
    var world:=WorldEnvironment.new();world.environment=env;root.add_child(world)
    var key:=DirectionalLight3D.new();key.light_energy=.78;key.rotation_degrees=Vector3(-34,-28,0);key.shadow_enabled=true;root.add_child(key)
    var fill:=OmniLight3D.new();fill.light_energy=.48;root.add_child(fill)
    var rim:=OmniLight3D.new();rim.light_energy=.36;root.add_child(rim)
    var camera:=Camera3D.new();camera.fov=32.0;camera.near=.01;camera.far=100.0;root.add_child(camera);camera.make_current()

    var specs:Array[Dictionary]=[
        {"name":"front","clip":"idle","time":0.0,"dir":Vector3(0,.03,1),"factor":.86},
        {"name":"three_quarter","clip":"idle","time":0.0,"dir":Vector3(.62,.04,1),"factor":.90},
        {"name":"side","clip":"idle","time":0.0,"dir":Vector3(1,.03,.03),"factor":.88},
        {"name":"back","clip":"idle","time":0.0,"dir":Vector3(0,.03,-1),"factor":.88},
        {"name":"idle","clip":"idle","time":.8,"dir":Vector3(.50,.04,1),"factor":.88},
        {"name":"run","clip":"run","time":.18,"dir":Vector3(.50,.04,1),"factor":.92},
        {"name":"jump","clip":"jump","time":.22,"dir":Vector3(.50,.04,1),"factor":.92},
        {"name":"wrench_swing","clip":"wrench_swing","time":.34,"dir":Vector3(.50,.04,1),"factor":.96},
        {"name":"victory","clip":"victory","time":.30,"dir":Vector3(.50,.04,1),"factor":.94},
    ]
    var captures:Array[Dictionary]=[]
    for spec in specs:
        if not pose(players,str(spec["clip"]),float(spec["time"])): fail("missing clip",receipt);return
        for _i in range(5): await process_frame
        var b:=bounds_of(imported)
        if b.size.length()<=.001: fail("invalid bounds",receipt);return
        var center:=b.get_center();var radius:=maxf(b.size.length()*.5,.05)
        fill.position=center+Vector3(-1,.5,1).normalized()*radius*2.2;fill.omni_range=radius*5
        rim.position=center+Vector3(1,.6,-1).normalized()*radius*2.4;rim.omni_range=radius*5
        var target:=center+Vector3(0,b.size.y*.03,b.size.z*.03)
        var distance:=radius/tan(deg_to_rad(camera.fov*.5))*float(spec["factor"])
        var direction:Vector3=(spec["dir"] as Vector3).normalized()
        var position:=target+direction*distance
        camera.look_at_from_position(position,target,Vector3.UP)
        for _i in range(7): await process_frame
        var path:="res://godot-kettlejack-v3-review-%s.png"%str(spec["name"])
        var cap:=capture(viewport,path)
        if cap.get("status")!="pass" or int(cap.get("png_bytes",0))<1200: fail("capture failed",receipt);return
        var m:Dictionary=cap["metrics"]
        if float(m["foreground_coverage"])<.06 or float(m["luma_range"])<.08: fail("technical framing failed",receipt);return
        captures.append({"name":spec["name"],"clip":spec["clip"],"time":spec["time"],"capture":cap})
    receipt["captures"]=captures;receipt["capture_count"]=captures.size();receipt["godot_version"]=Engine.get_version_info();receipt["status"]="pass"
    write_receipt(receipt)
    print("KETTLEJACK V0.3 REVIEW PASS ",JSON.stringify(receipt))
    viewport.queue_free();quit(0)
