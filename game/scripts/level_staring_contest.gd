extends Node2D
## Staring Contest — don't blink. Each blink plays the fahhh sound (this level only).

@onready var flash: ColorRect = $FlashOverlay
@onready var hud: Label = $UI/Hud
@onready var streak_label: Label = $UI/Streak
@onready var back_button: Button = $UI/BackButton
@onready var sfx: AudioStreamPlayer = $BlinkSfx

var _seen: int = 0
var _stare_sec: float = 0.0
var _best_stare: float = 0.0
var _flash: float = 0.0


func _ready() -> void:
	if sfx.stream == null:
		push_error("Staring Contest: BlinkSfx has no stream (check res://media/fahhh.wav)")
	back_button.pressed.connect(_on_back)
	if not EegBus.blink_detected.is_connected(_on_blink):
		EegBus.blink_detected.connect(_on_blink)
	_update_hud()


func _exit_tree() -> void:
	if EegBus.blink_detected.is_connected(_on_blink):
		EegBus.blink_detected.disconnect(_on_blink)


func _on_back() -> void:
	get_tree().change_scene_to_file("res://scenes/main.tscn")


func _unhandled_input(event: InputEvent) -> void:
	if event.is_action_pressed("ui_cancel"):
		_on_back()


func _process(delta: float) -> void:
	EegBus._drain_packets()
	_stare_sec += delta
	_best_stare = maxf(_best_stare, _stare_sec)
	if _flash > 0.0:
		_flash = maxf(0.0, _flash - delta)
		flash.color.a = clampf(_flash / 0.18, 0.0, 1.0) * 0.55
	else:
		flash.color.a = 0.0
	_update_hud()


func _on_blink(_z: float, _packet: Dictionary) -> void:
	_seen += 1
	_stare_sec = 0.0
	_flash = 0.18
	flash.color.a = 0.55
	if sfx.stream != null:
		sfx.stop()
		sfx.play()
	print("StaringContest blink → sfx  count=%d" % _seen)


func _update_hud() -> void:
	var link := "live" if EegBus.connected else "NO STREAM"
	var mode := "demo" if EegBus.demo and EegBus.connected else ("muse" if EegBus.connected else "offline")
	hud.text = "STARING CONTEST  ·  %s/%s\nblinks lose  ·  fahhh plays only here" % [link, mode]
	streak_label.text = "stare  %.1fs\nbest   %.1fs\nblinks %d (stream %d)" % [
		_stare_sec, _best_stare, _seen, EegBus.blink_count
	]
