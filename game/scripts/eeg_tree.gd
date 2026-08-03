extends Control
## Meditation tree — grows while calm stays high; wilts when distracted.

const TARGET_SEC := 60.0
const CALM_ENTER := 0.55
const CALM_EXIT := 0.48  # hysteresis so flicker doesn't thrash
const DECAY_SEC := 40.0  # full tree → stump if fully distracted this long

@onready var sky: ColorRect = $Sky
@onready var canopy: Control = $Canopy
@onready var hud: Label = $HUD
@onready var back_button: Button = $BackButton

var _sky_mat: ShaderMaterial
var _time: float = 0.0
var _blink_flash: float = 0.0
var _calm_s: float = 0.4
var _focus_s: float = 0.4
var _growth: float = 0.0  # 0..1 toward a full 60s tree
var _meditating: bool = false
var _session_meditate_sec: float = 0.0
var _wind: float = 0.0


func _ready() -> void:
	var sh: Shader = load("res://shaders/eeg_sky.gdshader") as Shader
	_sky_mat = ShaderMaterial.new()
	_sky_mat.shader = sh
	sky.material = _sky_mat
	back_button.pressed.connect(_on_back)
	if not EegBus.blink_detected.is_connected(_on_blink):
		EegBus.blink_detected.connect(_on_blink)
	canopy.draw.connect(_draw_tree)
	canopy.set_anchors_preset(Control.PRESET_FULL_RECT)
	canopy.mouse_filter = Control.MOUSE_FILTER_IGNORE


func _exit_tree() -> void:
	if EegBus.blink_detected.is_connected(_on_blink):
		EegBus.blink_detected.disconnect(_on_blink)


func _on_blink(_z: float, _packet: Dictionary) -> void:
	_blink_flash = 1.0


func _on_back() -> void:
	get_tree().change_scene_to_file("res://scenes/main.tscn")


func _process(delta: float) -> void:
	EegBus._drain_packets()
	_time += delta
	_blink_flash = maxf(0.0, _blink_flash - delta * 2.0)
	_wind = sin(_time * 0.7) * 0.02 + sin(_time * 1.3) * 0.01

	var calm_t := EegBus.calm
	var focus_t := EegBus.focus
	if not EegBus.connected:
		# Ambient: drifting calm so offline playtest still moves.
		calm_t = 0.42 + 0.28 * sin(_time * 0.21)
		focus_t = 0.35 + 0.25 * sin(_time * 0.33 + 0.8)

	var a := 1.0 - exp(-delta * 2.8)
	_calm_s = lerpf(_calm_s, calm_t, a)
	_focus_s = lerpf(_focus_s, focus_t, a)

	# Meditation: calm high and dominating focus a bit.
	var enter := _calm_s >= CALM_ENTER and _calm_s >= _focus_s * 0.95
	var stay := _calm_s >= CALM_EXIT and _calm_s + 0.05 >= _focus_s
	_meditating = enter if not _meditating else stay

	if _meditating:
		_growth = minf(1.0, _growth + delta / TARGET_SEC)
		_session_meditate_sec += delta
	else:
		_growth = maxf(0.0, _growth - delta / DECAY_SEC)

	if _sky_mat:
		_sky_mat.set_shader_parameter("u_time", _time)
		_sky_mat.set_shader_parameter("u_calm", _calm_s)
		_sky_mat.set_shader_parameter("u_growth", _growth)
		_sky_mat.set_shader_parameter("u_blink", _blink_flash)

	canopy.queue_redraw()

	var link := "live" if EegBus.connected else "ambient"
	var mode := "demo" if EegBus.demo and EegBus.connected else ("muse" if EegBus.connected else "no stream")
	var state := "growing" if _meditating else ("complete" if _growth >= 0.999 else "wilting")
	var secs_left := maxf(0.0, (1.0 - _growth) * TARGET_SEC)
	hud.text = (
		"MEDITATION TREE  ·  %s/%s\n"
		+ "calm %.2f   focus %.2f   growth %d%%   %s\n"
		+ "Need ~%.0fs more calm · threshold %.2f · wilts if distracted\n"
		+ "ESC / Back — hub"
	) % [link, mode, _calm_s, _focus_s, int(round(_growth * 100.0)), state, secs_left, CALM_ENTER]


func _draw_tree() -> void:
	var sz := canopy.size
	if sz.x < 8.0 or sz.y < 8.0:
		return

	var g := _growth
	if g < 0.004 and not _meditating:
		# Tiny seed / shoot hint.
		var seed_p := Vector2(sz.x * 0.5, sz.y * 0.88)
		canopy.draw_circle(seed_p + Vector2(0, -6), 3.0, Color(0.28, 0.42, 0.22, 0.7))
		return

	var base := Vector2(sz.x * 0.5, sz.y * 0.90)
	var max_len := sz.y * 0.42
	var length := max_len * smoothstep(0.0, 1.0, g)
	var depth := int(floor(2.0 + g * 7.0))  # 2..9
	var thickness := lerpf(3.0, 14.0, g)

	# Ground moss ring under trunk.
	canopy.draw_circle(base + Vector2(0, 4), lerpf(18.0, 54.0, g), Color(0.14, 0.22, 0.12, 0.55))

	_branch(base, -PI / 2.0 + _wind * (0.4 + g), length, depth, thickness, g, 0)


func _branch(
	pos: Vector2,
	angle: float,
	length: float,
	depth: int,
	width: float,
	g: float,
	gen: int
) -> void:
	if depth <= 0 or length < 2.5:
		_maybe_leaf(pos, g, gen)
		return

	var sway := _wind * (1.0 + float(gen) * 0.35) * (1.2 - 0.6 * _calm_s)
	var tip := pos + Vector2(cos(angle + sway), sin(angle + sway)) * length
	var bark := Color(
		lerpf(0.28, 0.18, g),
		lerpf(0.18, 0.12, g),
		lerpf(0.10, 0.07, g),
		1.0
	)
	canopy.draw_line(pos, tip, bark, maxf(1.2, width), true)

	var next_len := length * lerpf(0.68, 0.74, _calm_s)
	var next_w := width * 0.68
	var spread := lerpf(0.28, 0.48, 1.0 - _focus_s * 0.35)

	if depth >= 2:
		_branch(tip, angle - spread, next_len, depth - 1, next_w, g, gen + 1)
		_branch(tip, angle + spread * 0.92, next_len * 0.95, depth - 1, next_w, g, gen + 1)
		if g > 0.55 and depth >= 4 and gen % 2 == 0:
			_branch(tip, angle + spread * 0.15, next_len * 0.72, depth - 2, next_w * 0.85, g, gen + 1)
	else:
		_maybe_leaf(tip, g, gen)


func _maybe_leaf(pos: Vector2, g: float, gen: int) -> void:
	if g < 0.35:
		return
	var t := smoothstep(0.35, 0.85, g)
	var r := lerpf(2.0, 7.5, t) * (0.7 + 0.3 * sin(float(gen) + _time))
	var leaf := Color(
		lerpf(0.25, 0.18, t),
		lerpf(0.48, 0.62, t),
		lerpf(0.28, 0.32, t),
		lerpf(0.35, 0.92, t)
	)
	# Blink = brief blossom blush.
	leaf = leaf.lerp(Color(0.92, 0.55, 0.35, leaf.a), _blink_flash * 0.65)
	canopy.draw_circle(pos, r, leaf)
	if g > 0.75:
		canopy.draw_circle(pos + Vector2(r * 0.45, -r * 0.2), r * 0.55, leaf.lightened(0.15))


func _unhandled_input(event: InputEvent) -> void:
	if event.is_action_pressed("ui_cancel"):
		_on_back()
