extends Node2D
## Level 01 — Blink Flash
## White screen; flash red for FLASH_SEC on each detected blink.
## Goal right now: measure accuracy / latency of blink capture.

const FLASH_SEC := 0.05

@onready var screen: ColorRect = $Screen
@onready var hud: Label = $UI/Hud
@onready var back_button: Button = $UI/BackButton

var _flash_left: float = 0.0
var _seen: int = 0


func _ready() -> void:
	screen.color = Color.WHITE
	back_button.pressed.connect(func() -> void:
		get_tree().change_scene_to_file("res://scenes/main.tscn")
	)
	if not EegBus.blink_detected.is_connected(_on_blink):
		EegBus.blink_detected.connect(_on_blink)
	_update_hud()


func _exit_tree() -> void:
	if EegBus.blink_detected.is_connected(_on_blink):
		EegBus.blink_detected.disconnect(_on_blink)


func _process(delta: float) -> void:
	# Drain UDP every frame before other work (EegBus also drains in its _process).
	if _flash_left > 0.0:
		_flash_left = maxf(0.0, _flash_left - delta)
		screen.color = Color.RED if _flash_left > 0.0 else Color.WHITE
	_update_hud()


func _on_blink(z: float, _packet: Dictionary) -> void:
	_seen += 1
	_flash_left = FLASH_SEC
	screen.color = Color.RED
	print("Level01 blink flash z=%.2f count=%d" % [z, _seen])


func _update_hud() -> void:
	var link := "live" if EegBus.connected else "NO STREAM"
	var mode := "demo" if EegBus.demo else "muse"
	hud.text = "Blink Flash · seen %d · stream blinks %d · z=%.1f · [%s/%s] · flash %.0fms" % [
		_seen,
		EegBus.blink_count,
		EegBus.blink_z,
		link,
		mode,
		FLASH_SEC * 1000.0,
	]
