extends Node2D
## Main hub: HUD + Level 01 entry.

@onready var status_label: Label = $UI/Status
@onready var calm_bar: ProgressBar = $UI/CalmBar
@onready var focus_bar: ProgressBar = $UI/FocusBar
@onready var play_button: Button = $UI/PlayButton
@onready var flappy_button: Button = $UI/FlappyButton
@onready var fractal_button: Button = $UI/FractalButton
@onready var mood_button: Button = $UI/MoodButton
@onready var tree_button: Button = $UI/TreeButton


func _ready() -> void:
	play_button.pressed.connect(_on_play_pressed)
	flappy_button.pressed.connect(_on_flappy_pressed)
	fractal_button.pressed.connect(_on_fractal_pressed)
	mood_button.pressed.connect(_on_mood_pressed)
	tree_button.pressed.connect(_on_tree_pressed)
	EegBus.connection_changed.connect(_on_connection_changed)
	_on_connection_changed(EegBus.connected)


func _process(_delta: float) -> void:
	calm_bar.value = EegBus.calm * 100.0
	focus_bar.value = EegBus.focus * 100.0
	var mode := "demo" if EegBus.demo else "live"
	if EegBus.connected:
		status_label.text = "EEG linked (%s) · packets %d · age %.0f ms" % [
			mode, EegBus.packets_received, EegBus.last_packet_age_ms
		]
	else:
		status_label.text = "Waiting for EEG stream on UDP :%d…" % EegBus.port


func _on_connection_changed(connected: bool) -> void:
	play_button.disabled = false
	play_button.text = "Play Level 01 — Blink Flash" if connected else "Play Level 01 (offline)"


func _on_play_pressed() -> void:
	get_tree().change_scene_to_file("res://scenes/levels/level_01_still_waters.tscn")


func _on_flappy_pressed() -> void:
	get_tree().change_scene_to_file("res://scenes/levels/level_flappy_blink.tscn")


func _on_fractal_pressed() -> void:
	get_tree().change_scene_to_file("res://scenes/playground/eeg_fractals.tscn")


func _on_mood_pressed() -> void:
	get_tree().change_scene_to_file("res://scenes/playground/eeg_mood.tscn")


func _on_tree_pressed() -> void:
	get_tree().change_scene_to_file("res://scenes/playground/eeg_tree.tscn")
