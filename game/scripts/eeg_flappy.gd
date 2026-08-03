extends Node2D
## Blink Flappy — flap on each Muse blink (Space / click as backup).

const GRAVITY := 720.0
const FLAP_VY := -320.0
const PIPE_SPEED := 170.0
const PIPE_W := 78.0
const GAP := 220.0
const SPAWN_EVERY := 2.2
const BIRD_R := 18.0
const FLAP_REFRACTORY := 0.12
const VIEW_W := 1280.0
const VIEW_H := 720.0
const GROUND_Y := 640.0

@onready var hud: Label = $UI/Hud
@onready var hint: Label = $UI/Hint
@onready var back_button: Button = $UI/BackButton

var _bird: Vector2 = Vector2(320.0, 360.0)
var _vy: float = 0.0
var _pipes: Array = []  # each: {x, gap_y, scored}
var _spawn_t: float = 0.0
var _score: int = 0
var _best: int = 0
var _alive: bool = false
var _waiting: bool = true
var _flap_cd: float = 0.0
var _blink_flaps: int = 0
var _time: float = 0.0


func _ready() -> void:
	back_button.pressed.connect(_on_back)
	if not EegBus.blink_detected.is_connected(_on_blink):
		EegBus.blink_detected.connect(_on_blink)
	_reset(false)
	_update_labels()
	queue_redraw()


func _exit_tree() -> void:
	if EegBus.blink_detected.is_connected(_on_blink):
		EegBus.blink_detected.disconnect(_on_blink)


func _on_back() -> void:
	get_tree().change_scene_to_file("res://scenes/main.tscn")


func _on_blink(_z: float, _packet: Dictionary) -> void:
	_blink_flaps += 1
	_try_flap()


func _try_flap() -> void:
	if _flap_cd > 0.0:
		return
	_flap_cd = FLAP_REFRACTORY
	if _waiting:
		_start_run()
		return
	if not _alive:
		_reset(true)
		return
	_vy = FLAP_VY


func _start_run() -> void:
	_waiting = false
	_alive = true
	_vy = FLAP_VY
	_spawn_t = 0.4


func _reset(auto_start: bool) -> void:
	_bird = Vector2(320.0, 360.0)
	_vy = 0.0
	_pipes.clear()
	_spawn_t = 0.0
	_score = 0
	_alive = auto_start
	_waiting = not auto_start
	if auto_start:
		_start_run()
	queue_redraw()


func _unhandled_input(event: InputEvent) -> void:
	if event.is_action_pressed("ui_cancel"):
		_on_back()
		return
	if event.is_action_pressed("ui_accept") or event.is_action_pressed("ui_select"):
		_try_flap()
		return
	if event is InputEventMouseButton and event.pressed and event.button_index == MOUSE_BUTTON_LEFT:
		_try_flap()
	if event is InputEventKey and event.pressed and not event.echo and event.keycode == KEY_SPACE:
		_try_flap()


func _process(delta: float) -> void:
	EegBus._drain_packets()
	_time += delta
	_flap_cd = maxf(0.0, _flap_cd - delta)

	if _waiting:
		_bird.y = 360.0 + sin(_time * 2.4) * 14.0
		queue_redraw()
		_update_labels()
		return

	if not _alive:
		_update_labels()
		return

	_vy += GRAVITY * delta
	_bird.y += _vy * delta

	_spawn_t -= delta
	if _spawn_t <= 0.0:
		_spawn_t = SPAWN_EVERY
		_spawn_pipe()

	var i := 0
	while i < _pipes.size():
		var p: Dictionary = _pipes[i]
		p["x"] = float(p["x"]) - PIPE_SPEED * delta
		if not bool(p["scored"]) and float(p["x"]) + PIPE_W < _bird.x - BIRD_R:
			p["scored"] = true
			_score += 1
			_best = maxi(_best, _score)
		if float(p["x"]) + PIPE_W < -40.0:
			_pipes.remove_at(i)
			continue
		_pipes[i] = p
		i += 1

	if _bird.y + BIRD_R >= GROUND_Y or _bird.y - BIRD_R <= 0.0:
		_die()
	elif _hit_pipe():
		_die()

	queue_redraw()
	_update_labels()


func _spawn_pipe() -> void:
	var margin := 110.0
	var gap_y := randf_range(margin + GAP * 0.5, GROUND_Y - margin - GAP * 0.5)
	_pipes.append({"x": VIEW_W + 20.0, "gap_y": gap_y, "scored": false})


func _hit_pipe() -> bool:
	var bx := _bird.x
	var by := _bird.y
	for p in _pipes:
		var x0 := float(p["x"])
		var x1 := x0 + PIPE_W
		if bx + BIRD_R < x0 or bx - BIRD_R > x1:
			continue
		var gap_y := float(p["gap_y"])
		var top_h := gap_y - GAP * 0.5
		var bot_y := gap_y + GAP * 0.5
		if by - BIRD_R < top_h or by + BIRD_R > bot_y:
			return true
	return false


func _die() -> void:
	_alive = false
	_best = maxi(_best, _score)
	queue_redraw()


func _draw() -> void:
	# Sky + distant hills (drawn here so nothing covers the bird/pipes).
	draw_rect(Rect2(0.0, 0.0, VIEW_W, VIEW_H), Color(0.45, 0.72, 0.82, 1.0))
	draw_circle(Vector2(980.0, 120.0), 54.0, Color(0.98, 0.9, 0.55, 0.95))
	draw_colored_polygon(
		PackedVector2Array([
			Vector2(0.0, 520.0), Vector2(220.0, 440.0), Vector2(420.0, 510.0),
			Vector2(640.0, 430.0), Vector2(900.0, 500.0), Vector2(1280.0, 450.0),
			Vector2(1280.0, GROUND_Y), Vector2(0.0, GROUND_Y),
		]),
		Color(0.35, 0.58, 0.48, 0.55)
	)

	for p in _pipes:
		var x := float(p["x"])
		var gap_y := float(p["gap_y"])
		var top_h := gap_y - GAP * 0.5
		var bot_y := gap_y + GAP * 0.5
		var pipe_col := Color(0.18, 0.55, 0.38, 1.0)
		var lip := Color(0.12, 0.42, 0.28, 1.0)
		draw_rect(Rect2(x, 0.0, PIPE_W, top_h), pipe_col)
		draw_rect(Rect2(x - 6.0, top_h - 22.0, PIPE_W + 12.0, 22.0), lip)
		draw_rect(Rect2(x, bot_y, PIPE_W, GROUND_Y - bot_y), pipe_col)
		draw_rect(Rect2(x - 6.0, bot_y, PIPE_W + 12.0, 22.0), lip)

	var col := Color(0.95, 0.72, 0.22, 1.0)
	if not _alive and not _waiting:
		col = Color(0.75, 0.35, 0.22, 1.0)
	var angle := clampf(_vy / 900.0, -0.7, 1.1)
	draw_circle(_bird, BIRD_R, col)
	draw_circle(_bird + Vector2(7.0, -4.0), 4.5, Color(0.08, 0.1, 0.12, 1.0))
	var beak := PackedVector2Array([
		_bird + Vector2(BIRD_R - 2.0, -2.0).rotated(angle),
		_bird + Vector2(BIRD_R + 14.0, 2.0).rotated(angle),
		_bird + Vector2(BIRD_R - 2.0, 8.0).rotated(angle),
	])
	draw_colored_polygon(beak, Color(0.9, 0.4, 0.18, 1.0))

	draw_rect(Rect2(0.0, GROUND_Y, VIEW_W, VIEW_H - GROUND_Y), Color(0.22, 0.36, 0.18, 1.0))
	draw_rect(Rect2(0.0, GROUND_Y, VIEW_W, 8.0), Color(0.3, 0.48, 0.22, 1.0))


func _update_labels() -> void:
	var link := "live" if EegBus.connected else "NO STREAM"
	var mode := "demo" if EegBus.demo and EegBus.connected else ("muse" if EegBus.connected else "offline")
	var state := "ready" if _waiting else ("flying" if _alive else "crashed — blink to retry")
	hud.text = "BLINK FLAPPY  ·  %s/%s\nscore %d   best %d   blink-flaps %d   ·  %s" % [
		link, mode, _score, _best, _blink_flaps, state
	]
	if _waiting:
		hint.text = "Blink to flap · Space / click also work · ESC hub"
	elif not _alive:
		hint.text = "Ouch. Blink (or Space) to try again · ESC hub"
	else:
		hint.text = "Blink = flap · don't hit the green pipes · ESC hub"
