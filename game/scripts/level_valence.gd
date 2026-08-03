extends Node2D
## Mood Balance — steer frontal alpha asymmetry into a drifting target zone.

const TRACK_LEFT := 80.0
const TRACK_WIDTH := 1120.0
const TRACK_Y := 340.0
const ZONE_HALF := 0.11  # target half-width in valence units
const TARGET_SPEED := 0.18

@onready var screen: ColorRect = $Screen
@onready var track: ColorRect = $Track
@onready var zone: ColorRect = $Zone
@onready var cursor: ColorRect = $Cursor
@onready var left_label: Label = $UI/LeftLabel
@onready var right_label: Label = $UI/RightLabel
@onready var hud: Label = $UI/Hud
@onready var score_label: Label = $UI/Score
@onready var hint: Label = $UI/Hint
@onready var back_button: Button = $UI/BackButton

var _time: float = 0.0
var _valence_s: float = 0.5
var _target: float = 0.5
var _in_zone_sec: float = 0.0
var _best_streak: float = 0.0
var _streak: float = 0.0
var _score: float = 0.0


func _ready() -> void:
	back_button.pressed.connect(_on_back)
	_layout_static()
	_update_hud()


func _on_back() -> void:
	get_tree().change_scene_to_file("res://scenes/main.tscn")


func _unhandled_input(event: InputEvent) -> void:
	if event.is_action_pressed("ui_cancel"):
		_on_back()


func _layout_static() -> void:
	track.position = Vector2(TRACK_LEFT, TRACK_Y)
	track.size = Vector2(TRACK_WIDTH, 28.0)
	cursor.size = Vector2(10.0, 48.0)
	zone.size = Vector2(TRACK_WIDTH * ZONE_HALF * 2.0, 28.0)


func _process(delta: float) -> void:
	EegBus._drain_packets()
	_time += delta

	var valence_t := EegBus.valence
	if not EegBus.connected:
		# Offline/ambient drift so the level is playable without a headset.
		valence_t = 0.5 + 0.35 * sin(_time * 0.55)

	var a := 1.0 - exp(-delta / 1.2)
	_valence_s = lerpf(_valence_s, valence_t, a)

	# Slow drifting target with mild random walk.
	_target += sin(_time * 0.37) * TARGET_SPEED * delta
	_target += sin(_time * 0.91 + 1.3) * TARGET_SPEED * 0.55 * delta
	_target = clampf(_target, ZONE_HALF + 0.05, 1.0 - ZONE_HALF - 0.05)

	var in_zone := absf(_valence_s - _target) <= ZONE_HALF
	if in_zone:
		_streak += delta
		_in_zone_sec += delta
		_score += delta * (1.0 + _streak * 0.15)
		_best_streak = maxf(_best_streak, _streak)
		zone.color = Color(0.45, 0.72, 0.58, 0.55)
		cursor.color = Color(0.85, 0.95, 0.88, 1.0)
	else:
		_streak = 0.0
		zone.color = Color(0.55, 0.62, 0.88, 0.35)
		cursor.color = Color(0.92, 0.78, 0.45, 1.0)

	_place_on_track(zone, _target, zone.size.x)
	_place_on_track(cursor, _valence_s, cursor.size.x)
	cursor.position.y = TRACK_Y - 10.0

	# Background tint: cool (withdraw) ↔ warm (approach).
	var cool := Color(0.06, 0.09, 0.14, 1.0)
	var warm := Color(0.14, 0.09, 0.06, 1.0)
	screen.color = cool.lerp(warm, _valence_s)

	_update_hud()


func _place_on_track(node: ColorRect, t: float, width: float) -> void:
	var x := TRACK_LEFT + TRACK_WIDTH * clampf(t, 0.0, 1.0) - width * 0.5
	node.position = Vector2(x, TRACK_Y)


func _update_hud() -> void:
	var link := "live" if EegBus.connected else "NO STREAM"
	var mode := "demo" if EegBus.demo and EegBus.connected else ("muse" if EegBus.connected else "offline")
	hud.text = "MOOD BALANCE  ·  %s/%s\nFAA valence steers the marker  ·  stay in the zone" % [link, mode]
	score_label.text = "score   %.0f\nstreak  %.1fs\nbest    %.1fs\nin zone %.0f%%" % [
		_score,
		_streak,
		_best_streak,
		(100.0 * _in_zone_sec / maxf(_time, 0.01)),
	]
	left_label.text = "withdraw"
	right_label.text = "approach"
	hint.text = "Feel toward the glowing zone (AF7/AF8 alpha asymmetry).\nESC / Back — hub"
