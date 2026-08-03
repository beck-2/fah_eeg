extends Control
## mind games hub — entry + live calm/focus/valence meters.

@onready var bg: ColorRect = $Bg
@onready var status_label: Label = $Status
@onready var calm_fill: ColorRect = $Meters/CalmTrack/CalmFill
@onready var focus_fill: ColorRect = $Meters/FocusTrack/FocusFill
@onready var valence_fill: ColorRect = $Meters/ValenceTrack/ValenceFill
@onready var calm_value: Label = $Meters/CalmValue
@onready var focus_value: Label = $Meters/FocusValue
@onready var valence_value: Label = $Meters/ValenceValue

@onready var play_button: Button = $Nav/PlayCol/PlayButton
@onready var flappy_button: Button = $Nav/PlayCol/FlappyButton
@onready var stare_button: Button = $Nav/PlayCol/StareButton
@onready var valence_button: Button = $Nav/PlayCol/ValenceButton
@onready var fractal_button: Button = $Nav/ArtCol/FractalButton
@onready var mood_button: Button = $Nav/ArtCol/MoodButton
@onready var tree_button: Button = $Nav/ArtCol/TreeButton

var _mat: ShaderMaterial
var _time: float = 0.0
var _calm_s: float = 0.0
var _focus_s: float = 0.0
var _valence_s: float = 0.5


func _ready() -> void:
	var sh: Shader = load("res://shaders/hub_bg.gdshader") as Shader
	_mat = ShaderMaterial.new()
	_mat.shader = sh
	bg.material = _mat

	play_button.pressed.connect(_on_play_pressed)
	flappy_button.pressed.connect(_on_flappy_pressed)
	stare_button.pressed.connect(_on_stare_pressed)
	valence_button.pressed.connect(_on_valence_pressed)
	fractal_button.pressed.connect(_on_fractal_pressed)
	mood_button.pressed.connect(_on_mood_pressed)
	tree_button.pressed.connect(_on_tree_pressed)
	EegBus.connection_changed.connect(_on_connection_changed)
	_on_connection_changed(EegBus.connected)
	_apply_type()


func _apply_type() -> void:
	# Prefer distinctive system faces over the default UI font.
	var display := SystemFont.new()
	display.font_names = PackedStringArray(["Avenir Next", "Futura", "Gill Sans", "Helvetica Neue"])
	display.font_weight = 700
	var body := SystemFont.new()
	body.font_names = PackedStringArray(["Avenir Next", "Helvetica Neue", "Gill Sans"])
	body.font_weight = 400
	$Brand.add_theme_font_override("font", display)
	status_label.add_theme_font_override("font", body)
	$Meters/CalmLabel.add_theme_font_override("font", body)
	$Meters/FocusLabel.add_theme_font_override("font", body)
	$Meters/ValenceLabel.add_theme_font_override("font", body)
	calm_value.add_theme_font_override("font", body)
	focus_value.add_theme_font_override("font", body)
	valence_value.add_theme_font_override("font", body)
	$Nav/PlayHeading.add_theme_font_override("font", body)
	$Nav/ArtHeading.add_theme_font_override("font", body)


func _process(delta: float) -> void:
	EegBus._drain_packets()
	_time += delta
	var a := 1.0 - exp(-delta / 2.0)
	_calm_s = lerpf(_calm_s, EegBus.calm, a)
	_focus_s = lerpf(_focus_s, EegBus.focus, a)
	_valence_s = lerpf(_valence_s, EegBus.valence, a)

	if _mat:
		_mat.set_shader_parameter("u_time", _time)
		_mat.set_shader_parameter("u_calm", _calm_s)
		_mat.set_shader_parameter("u_focus", _focus_s)

	_set_meter(calm_fill, _calm_s)
	_set_meter(focus_fill, _focus_s)
	_set_meter(valence_fill, _valence_s)
	calm_value.text = "%.0f" % (_calm_s * 100.0)
	focus_value.text = "%.0f" % (_focus_s * 100.0)
	valence_value.text = "%.0f" % (_valence_s * 100.0)

	if EegBus.connected:
		var mode := "demo" if EegBus.demo else "muse"
		status_label.text = "linked · %s · %d pkt · %.0f ms" % [
			mode, EegBus.packets_received, EegBus.last_packet_age_ms
		]
	else:
		status_label.text = "waiting for stream on :%d" % EegBus.port


func _set_meter(fill: ColorRect, amount: float) -> void:
	var track: ColorRect = fill.get_parent() as ColorRect
	var w := track.size.x
	if w <= 1.0:
		w = 320.0
	fill.offset_right = fill.offset_left + w * clampf(amount, 0.0, 1.0)


func _on_connection_changed(_connected: bool) -> void:
	pass


func _on_play_pressed() -> void:
	get_tree().change_scene_to_file("res://scenes/levels/level_01_still_waters.tscn")


func _on_flappy_pressed() -> void:
	get_tree().change_scene_to_file("res://scenes/levels/level_flappy_blink.tscn")


func _on_stare_pressed() -> void:
	get_tree().change_scene_to_file("res://scenes/levels/level_staring_contest.tscn")


func _on_valence_pressed() -> void:
	get_tree().change_scene_to_file("res://scenes/levels/level_valence.tscn")


func _on_fractal_pressed() -> void:
	get_tree().change_scene_to_file("res://scenes/playground/eeg_fractals.tscn")


func _on_mood_pressed() -> void:
	get_tree().change_scene_to_file("res://scenes/playground/eeg_mood.tscn")


func _on_tree_pressed() -> void:
	get_tree().change_scene_to_file("res://scenes/playground/eeg_tree.tscn")
