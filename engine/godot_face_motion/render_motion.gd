extends SceneTree

const ASSET_PATH: String = "res://generated/sentinel_hm08_face_motion_v0_1.gltf"
const OUTPUT_DIR: String = "res://visual_evidence"
const FRAME_SIZE := Vector2i(768, 768)
const FACE_CENTER := Vector3(0.0, 0.720, 0.105)
const CAMERA_POSITION := Vector3(0.0, 0.720, 0.440)
const LEFT_EYE_CENTER := Vector3(0.030775, 0.728415, 0.124535)
const RIGHT_EYE_CENTER := Vector3(-0.030775, 0.728415, 0.124535)
const EYE_RADIUS_M := 0.013815
const POSES: Array[Dictionary] = [
    {"name": "neutral", "weights": {}},
    {"name": "blink", "weights": {"left_blink": 1.0, "right_blink": 1.0}},
    {"name": "smile", "weights": {"smile": 0.80}},
    {"name": "jaw_open", "weights": {"jaw_open": 0.70}},
]

func fail(message: String) -> void:
    push_error(message)
    quit(1)

func collect_meshes(node: Node, out: Array[MeshInstance3D]) -> void:
    if node is MeshInstance3D:
        out.append(node as MeshInstance3D)
    for child: Node in node.get_children():
        collect_meshes(child, out)

func reset_weights(meshes: Array[MeshInstance3D]) -> void:
    for mesh_node: MeshInstance3D in meshes:
        if mesh_node.mesh == null:
            continue
        for index: int in range(mesh_node.mesh.get_blend_shape_count()):
            var target_name: String = str(mesh_node.mesh.get_blend_shape_name(index))
            mesh_node.set("blend_shapes/" + target_name, 0.0)

func set_pose(meshes: Array[MeshInstance3D], weights: Dictionary) -> void:
    reset_weights(meshes)
    for target_value: Variant in weights.keys():
        var target_name: String = str(target_value)
        var applied := false
        for mesh_node: MeshInstance3D in meshes:
            if mesh_node.mesh == null:
                continue
            for index: int in range(mesh_node.mesh.get_blend_shape_count()):
                if str(mesh_node.mesh.get_blend_shape_name(index)) == target_name:
                    mesh_node.set("blend_shapes/" + target_name, float(weights[target_value]))
                    applied = true
                    break
            if applied:
                break
        if not applied:
            fail("Could not apply render pose target %s" % target_name)
            return

func make_material(color: Color, roughness: float) -> StandardMaterial3D:
    var material := StandardMaterial3D.new()
    material.albedo_color = color
    material.metallic = 0.0
    material.roughness = roughness
    return material

func add_eye(world: Node3D, center: Vector3, label: String) -> void:
    var sclera_mesh := SphereMesh.new()
    sclera_mesh.radius = EYE_RADIUS_M
    sclera_mesh.height = EYE_RADIUS_M * 2.0
    sclera_mesh.radial_segments = 32
    sclera_mesh.rings = 16
    var sclera := MeshInstance3D.new()
    sclera.name = label + "_Sclera"
    sclera.mesh = sclera_mesh
    sclera.material_override = make_material(Color(0.78, 0.80, 0.76, 1.0), 0.38)
    sclera.position = center
    world.add_child(sclera)

    var iris_mesh := CylinderMesh.new()
    iris_mesh.top_radius = EYE_RADIUS_M * 0.38
    iris_mesh.bottom_radius = EYE_RADIUS_M * 0.38
    iris_mesh.height = 0.00055
    iris_mesh.radial_segments = 32
    var iris := MeshInstance3D.new()
    iris.name = label + "_Iris"
    iris.mesh = iris_mesh
    iris.material_override = make_material(Color(0.18, 0.30, 0.33, 1.0), 0.30)
    iris.position = center + Vector3(0.0, 0.0, EYE_RADIUS_M * 0.93)
    iris.rotation_degrees = Vector3(90.0, 0.0, 0.0)
    world.add_child(iris)

    var pupil_mesh := CylinderMesh.new()
    pupil_mesh.top_radius = EYE_RADIUS_M * 0.16
    pupil_mesh.bottom_radius = EYE_RADIUS_M * 0.16
    pupil_mesh.height = 0.00065
    pupil_mesh.radial_segments = 24
    var pupil := MeshInstance3D.new()
    pupil.name = label + "_Pupil"
    pupil.mesh = pupil_mesh
    pupil.material_override = make_material(Color(0.012, 0.014, 0.016, 1.0), 0.22)
    pupil.position = center + Vector3(0.0, 0.0, EYE_RADIUS_M * 0.955)
    pupil.rotation_degrees = Vector3(90.0, 0.0, 0.0)
    world.add_child(pupil)

func _initialize() -> void:
    call_deferred("_render_all")

func _render_all() -> void:
    if not FileAccess.file_exists(ASSET_PATH):
        fail("hm08 face-motion glTF does not exist")
        return

    DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(OUTPUT_DIR))

    var document := GLTFDocument.new()
    var state := GLTFState.new()
    var error := document.append_from_file(ASSET_PATH, state)
    if error != OK:
        fail("Godot rejected hm08 face-motion glTF for visual render")
        return
    var instance := document.generate_scene(state)
    if instance == null:
        fail("Godot generated no hm08 face-motion scene for visual render")
        return

    var viewport := SubViewport.new()
    viewport.name = "FaceMotionEvidenceViewport"
    viewport.size = FRAME_SIZE
    viewport.render_target_update_mode = SubViewport.UPDATE_ALWAYS
    viewport.render_target_clear_mode = SubViewport.CLEAR_MODE_ALWAYS
    viewport.transparent_bg = false
    viewport.msaa_3d = Viewport.MSAA_4X
    get_root().add_child(viewport)

    var world := Node3D.new()
    world.name = "EvidenceWorld"
    viewport.add_child(world)
    world.add_child(instance)
    add_eye(world, LEFT_EYE_CENTER, "Left")
    add_eye(world, RIGHT_EYE_CENTER, "Right")

    var environment := WorldEnvironment.new()
    environment.environment = Environment.new()
    environment.environment.background_mode = Environment.BG_COLOR
    environment.environment.background_color = Color(0.025, 0.030, 0.038, 1.0)
    environment.environment.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
    environment.environment.ambient_light_color = Color(0.46, 0.50, 0.56, 1.0)
    environment.environment.ambient_light_energy = 0.16
    world.add_child(environment)

    var camera := Camera3D.new()
    camera.name = "EvidenceCamera"
    camera.position = CAMERA_POSITION
    camera.fov = 34.0
    camera.near = 0.05
    camera.far = 5.0
    world.add_child(camera)
    camera.look_at(FACE_CENTER, Vector3.UP)
    camera.current = true

    var key := OmniLight3D.new()
    key.name = "KeyLight"
    key.position = Vector3(-0.18, 0.82, 0.38)
    key.light_color = Color(1.0, 0.91, 0.84, 1.0)
    key.light_energy = 0.82
    key.omni_range = 1.6
    key.shadow_enabled = false
    world.add_child(key)

    var fill := OmniLight3D.new()
    fill.name = "FillLight"
    fill.position = Vector3(0.21, 0.70, 0.34)
    fill.light_color = Color(0.62, 0.76, 1.0, 1.0)
    fill.light_energy = 0.26
    fill.omni_range = 1.4
    fill.shadow_enabled = false
    world.add_child(fill)

    var rim := OmniLight3D.new()
    rim.name = "RimLight"
    rim.position = Vector3(0.0, 0.84, -0.02)
    rim.light_color = Color(0.78, 0.88, 1.0, 1.0)
    rim.light_energy = 0.18
    rim.omni_range = 1.0
    rim.shadow_enabled = false
    world.add_child(rim)

    var meshes: Array[MeshInstance3D] = []
    collect_meshes(instance, meshes)
    if meshes.is_empty():
        fail("No imported MeshInstance3D found for visual evidence")
        return

    await process_frame
    await process_frame
    await process_frame

    var receipt := {
        "schema": "axm.game-assets.godot-hm08-face-motion-visual.v0.2",
        "asset": ASSET_PATH,
        "frame_size": [FRAME_SIZE.x, FRAME_SIZE.y],
        "camera_position": [CAMERA_POSITION.x, CAMERA_POSITION.y, CAMERA_POSITION.z],
        "face_center": [FACE_CENTER.x, FACE_CENTER.y, FACE_CENTER.z],
        "render_only_eye_landmarks": {
            "left": [LEFT_EYE_CENTER.x, LEFT_EYE_CENTER.y, LEFT_EYE_CENTER.z],
            "right": [RIGHT_EYE_CENTER.x, RIGHT_EYE_CENTER.y, RIGHT_EYE_CENTER.z],
            "radius_m": EYE_RADIUS_M,
            "source": "pinned hm08 eye-landmarks.json"
        },
        "poses": [],
        "truth": "Rendered Godot frames are visual evidence for human/observer review. Render-only eyes restore the pinned hm08 helper-eye geometry for motion legibility without changing the exported motion source. Frame existence does not automatically approve facial-motion quality."
    }

    for pose: Dictionary in POSES:
        set_pose(meshes, pose["weights"] as Dictionary)
        await process_frame
        await process_frame
        await process_frame
        RenderingServer.force_draw()
        var image := viewport.get_texture().get_image()
        if image == null or image.is_empty():
            fail("Godot returned an empty image for pose %s" % str(pose["name"]))
            return
        var output_path := OUTPUT_DIR.path_join(str(pose["name"]) + ".png")
        var save_error := image.save_png(output_path)
        if save_error != OK:
            fail("Could not save render pose %s" % str(pose["name"]))
            return
        receipt["poses"].append({
            "name": str(pose["name"]),
            "weights": pose["weights"],
            "file": output_path.get_file(),
            "width": image.get_width(),
            "height": image.get_height(),
        })

    var receipt_path := OUTPUT_DIR.path_join("visual-receipt.json")
    var receipt_file := FileAccess.open(receipt_path, FileAccess.WRITE)
    if receipt_file == null:
        fail("Could not write visual evidence receipt")
        return
    receipt_file.store_string(JSON.stringify(receipt, "  ") + "\n")
    receipt_file.close()
    print("AXM GODOT HM08 FACE MOTION VISUAL EVIDENCE PASS ", JSON.stringify(receipt))
    quit(0)
