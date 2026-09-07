extends SceneTree

const ASSET_PATH: String = "res://generated/sentinel_rifle.gltf"
const RENDER_PATH: String = "res://godot-render.png"
const RECEIPT_PATH: String = "res://godot-render-receipt.json"
const SIZE: Vector2i = Vector2i(640, 640)

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

func _initialize() -> void:
    var receipt: Dictionary = {
        "schema": "axm.game-assets.godot-render.v0.2",
        "asset": ASSET_PATH,
        "truth": "Real Godot-rendered screenshot and pixel evidence. Pixel heuristics prove visible rendered signal, not aesthetic quality."
    }
    if not FileAccess.file_exists(ASSET_PATH):
        fail("Generated glTF fixture does not exist", receipt)
        return

    RenderingServer.set_default_clear_color(Color(0.025, 0.032, 0.045, 1.0))

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

    var scene_root: Node3D = Node3D.new()
    scene_root.name = "AXM_Render_Proof"
    get_root().add_child(scene_root)
    scene_root.add_child(imported)

    var key: DirectionalLight3D = DirectionalLight3D.new()
    key.light_energy = 1.9
    key.rotation_degrees = Vector3(-48.0, -32.0, 0.0)
    key.shadow_enabled = true
    scene_root.add_child(key)

    var fill: OmniLight3D = OmniLight3D.new()
    fill.position = Vector3(-0.6, 0.55, 1.0)
    fill.omni_range = 4.0
    fill.light_energy = 3.0
    scene_root.add_child(fill)

    var rim: OmniLight3D = OmniLight3D.new()
    rim.position = Vector3(0.9, 0.35, -0.8)
    rim.omni_range = 3.5
    rim.light_energy = 2.2
    scene_root.add_child(rim)

    var camera: Camera3D = Camera3D.new()
    camera.position = Vector3(1.45, 0.62, 1.45)
    camera.fov = 42.0
    scene_root.add_child(camera)
    camera.look_at(Vector3(0.10, -0.06, 0.0), Vector3.UP)
    camera.current = true

    for _frame: int in range(8):
        await process_frame

    var viewport: Window = get_root()
    var image: Image = viewport.get_texture().get_image()
    if image == null or image.is_empty():
        fail("Godot viewport produced no image", receipt)
        return
    var save_error: int = image.save_png(RENDER_PATH)
    if save_error != OK:
        fail("Godot could not save render PNG: %s" % save_error, receipt)
        return

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
    var luma_range: float = max_luma - min_luma
    var png_bytes: int = FileAccess.get_file_as_bytes(RENDER_PATH).size()
    receipt["godot_version"] = Engine.get_version_info()
    receipt["image"] = {
        "path": RENDER_PATH,
        "width": width,
        "height": height,
        "png_bytes": png_bytes
    }
    receipt["sampled_pixels"] = sampled
    receipt["foreground_pixels"] = foreground
    receipt["foreground_coverage"] = coverage
    receipt["luma_min"] = min_luma
    receipt["luma_max"] = max_luma
    receipt["luma_mean"] = luma_sum / float(maxi(sampled, 1))
    receipt["luma_range"] = luma_range
    receipt["background_sample"] = [background.r, background.g, background.b, background.a]

    if width != SIZE.x or height != SIZE.y:
        fail("Unexpected render dimensions %sx%s" % [width, height], receipt)
        return
    if png_bytes <= 1000:
        fail("Rendered PNG is unexpectedly small: %s bytes" % png_bytes, receipt)
        return
    if coverage < 0.015:
        fail("Rendered asset coverage too small: %s" % coverage, receipt)
        return
    if luma_range < 0.10:
        fail("Rendered image lacks visible contrast: %s" % luma_range, receipt)
        return

    receipt["status"] = "pass"
    write_receipt(receipt)
    print("AXM GODOT RENDER PASS ", JSON.stringify(receipt))
    scene_root.queue_free()
    quit(0)
