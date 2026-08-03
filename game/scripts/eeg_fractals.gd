extends Control
## Fun EEG-driven Julia fractal playground (not a level).

@onready var fractal: ColorRect = $Fractal
@onready var hud: Label = $HUD
@onready var back_button: Button = $BackButton

var _mat: ShaderMaterial
var _time: float = 0.0
var _zoom: float = 1.25
var _center: Vector2 = Vector2(0.05, 0.0)
var _blink_flash: float = 0.0
var _zoom_punch: float = 0.0
var _c_orbit: float = 0.0


func _ready() -> void:
	var sh: Shader = load("res://shaders/eeg_julia.gdshader") as Shader
	_mat = ShaderMaterial.new()
	_mat.shader = sh
	fractal.material = _mat
	back_button.pressed.connect(_on_back)
	if not EegBus.blink_detected.is_connected(_on_blink):
		EegBus.blink_detected.connect(_on_blink)
	_update_aspect()
	get_viewport().size_changed.connect(_update_aspect)


func _exit_tree() -> void:
	if EegBus.blink_detected.is_connected(_on_blink):
		EegBus.blink_detected.disconnect(_on_blink)


func _update_aspect() -> void:
	var sz := get_viewport_rect().size
	if _mat and sz.y > 0.0:
		_mat.set_shader_parameter("u_aspect", sz.x / sz.y)


func _on_blink(_z: float, _packet: Dictionary) -> void:
	_blink_flash = 1.0
	_zoom_punch = 0.55


func _on_back() -> void:
	get_tree().change_scene_to_file("res://scenes/main.tscn")


func _process(delta: float) -> void:
	EegBus._drain_packets()
	_time += delta
	_blink_flash = maxf(0.0, _blink_flash - delta * 2.4)
	_zoom_punch = maxf(0.0, _zoom_punch - delta * 1.6)

	var calm := EegBus.calm
	var focus := EegBus.focus
	# Offline ambient drift so the fractal still breathes without a stream.
	if not EegBus.connected:
		calm = 0.45 + 0.35 * sin(_time * 0.37)
		focus = 0.4 + 0.4 * sin(_time * 0.61 + 1.2)

	# Orbit Julia-c: focus spins faster / widens the loop.
	_c_orbit += delta * (0.22 + 1.4 * focus)
	var rad := 0.22 + 0.35 * focus
	var cx := -0.745 + rad * cos(_c_orbit)
	var cy := 0.12 + rad * 0.72 * sin(_c_orbit * 1.37)
	# Calm nudges toward a "breathing" classic Julia seed.
	cx = lerpf(cx, -0.8, calm * 0.35)
	cy = lerpf(cy, 0.156, calm * 0.35)

	# Zoom: calm eases outward serenity; blink punches inward.
	var target_zoom := 1.05 + calm * 0.85 - focus * 0.15 + _zoom_punch
	_zoom = lerpf(_zoom, target_zoom, 1.0 - exp(-delta * 2.5))
	_center = _center.lerp(Vector2(0.02 * sin(_time * 0.2), 0.02 * cos(_time * 0.17)), delta)

	if _mat:
		_mat.set_shader_parameter("u_time", _time)
		_mat.set_shader_parameter("u_c", Vector2(cx, cy))
		_mat.set_shader_parameter("u_zoom", _zoom)
		_mat.set_shader_parameter("u_center", _center)
		_mat.set_shader_parameter("u_calm", calm)
		_mat.set_shader_parameter("u_focus", focus)
		_mat.set_shader_parameter("u_blink", _blink_flash)

	var link := "live" if EegBus.connected else "ambient"
	var mode := "demo" if EegBus.demo and EegBus.connected else ("muse" if EegBus.connected else "no stream")
	hud.text = "FRACTAL PLAYGROUND  ·  %s/%s\ncalm %.2f   focus %.2f   blinks %d\nESC / Back — hub" % [
		link, mode, calm, focus, EegBus.blink_count
	]


func _unhandled_input(event: InputEvent) -> void:
	if event.is_action_pressed("ui_cancel"):
		_on_back()
