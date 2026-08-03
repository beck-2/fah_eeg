extends Control
## Calm ↔ focus morphing mood field (playground / not a level).

@onready var field: ColorRect = $Field
@onready var hud: Label = $HUD
@onready var back_button: Button = $BackButton

var _mat: ShaderMaterial
var _time: float = 0.0
var _blink_flash: float = 0.0
var _calm_s: float = 0.45
var _focus_s: float = 0.4


func _ready() -> void:
	var sh: Shader = load("res://shaders/eeg_mood.gdshader") as Shader
	_mat = ShaderMaterial.new()
	_mat.shader = sh
	field.material = _mat
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


func _on_back() -> void:
	get_tree().change_scene_to_file("res://scenes/main.tscn")


func _process(delta: float) -> void:
	EegBus._drain_packets()
	_time += delta
	_blink_flash = maxf(0.0, _blink_flash - delta * 2.2)

	var calm_t := EegBus.calm
	var focus_t := EegBus.focus
	if not EegBus.connected:
		# Ambient: slow drift for offline playtest.
		calm_t = 0.48 + 0.22 * sin(_time * 0.12)
		focus_t = 0.42 + 0.22 * sin(_time * 0.17 + 1.7)

	# Extra display smoothing (~2.5 s) on top of stream EMA.
	var a := 1.0 - exp(-delta / 2.5)
	_calm_s = lerpf(_calm_s, calm_t, a)
	_focus_s = lerpf(_focus_s, focus_t, a)

	if _mat:
		_mat.set_shader_parameter("u_time", _time)
		_mat.set_shader_parameter("u_calm", _calm_s)
		_mat.set_shader_parameter("u_focus", _focus_s)
		_mat.set_shader_parameter("u_blink", _blink_flash)

	var link := "live" if EegBus.connected else "ambient"
	var mode := "demo" if EegBus.demo and EegBus.connected else ("muse" if EegBus.connected else "no stream")
	hud.text = "MOOD FIELD  ·  %s/%s\ncalm %.2f   focus %.2f   blinks %d\ncool flow ← calm · focus → warm energy · blink flashes\nESC / Back — hub" % [
		link, mode, _calm_s, _focus_s, EegBus.blink_count
	]


func _unhandled_input(event: InputEvent) -> void:
	if event.is_action_pressed("ui_cancel"):
		_on_back()
