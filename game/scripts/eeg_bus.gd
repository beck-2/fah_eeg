extends Node
## Global EEG feature bus. Receives UDP packets from the Python streamer.

signal features_updated(features: Dictionary)
signal blink_detected(z: float, packet: Dictionary)
signal connection_changed(connected: bool)

const DEFAULT_PORT := 14141

var port: int = DEFAULT_PORT
var calm: float = 0.0
var focus: float = 0.0
var valence: float = 0.5
var faa: float = 0.0
var blink: float = 0.0
var blink_z: float = 0.0
var blink_count: int = 0
var bands: Dictionary = {}
var demo: bool = false
var last_packet_age_ms: float = INF
var connected: bool = false
var packets_received: int = 0

var _udp: PacketPeerUDP
var _last_packet_usec: int = 0
var _was_connected: bool = false


func _ready() -> void:
	process_priority = -100  # Drain UDP before level scripts each frame.
	_udp = PacketPeerUDP.new()
	var err := _udp.bind(port)
	if err != OK:
		push_error("EegBus: failed to bind UDP port %d (err %s)" % [port, err])
	else:
		print("EegBus listening on 127.0.0.1:%d" % port)


func _process(_delta: float) -> void:
	_drain_packets()
	if _last_packet_usec == 0:
		last_packet_age_ms = INF
	else:
		last_packet_age_ms = float(Time.get_ticks_usec() - _last_packet_usec) / 1000.0
	connected = last_packet_age_ms < 750.0
	if connected != _was_connected:
		_was_connected = connected
		connection_changed.emit(connected)


func _drain_packets() -> void:
	if _udp == null:
		return
	while _udp.get_available_packet_count() > 0:
		var bytes := _udp.get_packet()
		var text := bytes.get_string_from_utf8()
		var data = JSON.parse_string(text)
		if typeof(data) != TYPE_DICTIONARY:
			continue
		var ptype := str(data.get("type", ""))
		if ptype == "blink_event":
			_apply_blink(data)
		elif ptype == "eeg_features":
			_apply_features(data)


func _apply_blink(data: Dictionary) -> void:
	packets_received += 1
	_last_packet_usec = Time.get_ticks_usec()
	demo = bool(data.get("demo", false))
	blink = 1.0
	blink_z = float(data.get("blink_z", 0.0))
	blink_count = int(data.get("n", blink_count + 1))
	blink_detected.emit(blink_z, data)


func _apply_features(data: Dictionary) -> void:
	packets_received += 1
	_last_packet_usec = Time.get_ticks_usec()
	calm = clampf(float(data.get("calm", 0.0)), 0.0, 1.0)
	focus = clampf(float(data.get("focus", 0.0)), 0.0, 1.0)
	valence = clampf(float(data.get("valence", 0.5)), 0.0, 1.0)
	faa = float(data.get("faa", 0.0))
	demo = bool(data.get("demo", false))
	if data.has("blinks"):
		blink_count = int(data.get("blinks", blink_count))
	var b = data.get("bands", {})
	if typeof(b) == TYPE_DICTIONARY:
		bands = b
	features_updated.emit(data)


func reset_metrics() -> void:
	calm = 0.0
	focus = 0.0
	valence = 0.5
	faa = 0.0
	blink = 0.0
	blink_z = 0.0
	blink_count = 0
	bands = {}
	packets_received = 0
	_last_packet_usec = 0
