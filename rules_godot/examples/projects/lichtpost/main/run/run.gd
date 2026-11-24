extends Node3D
## Reusable fixed-tick round. The supplied level contains data, not behavior.

signal finished(state: Dictionary)
signal event_happened(event: String)
const Route = preload("res://main/rules/route_model.gd")
const Replay = preload("res://main/rules/replay.gd")
const LevelDefinition = preload("res://main/run/level_definition.gd")
const RunView = preload("res://main/run/view/run_view.gd")
const Sound = preload("res://main/components/sound/sound.gd")
## Seconds per rule tick: the route model runs at a fixed 60 Hz.
const TICK := 1.0 / 60.0
@onready var view: RunView = $View
@onready var sound: Sound = $SoundCues
var model: Route = Route.new()
var level: LevelDefinition
var replay: Replay = null
var replay_held := false
var keyboard_held := false
var touch_id := -1
var pending_press := false
var clock := 0.0
var paused := false
var active := false
var view_ready := false
## Model position before the latest tick; the view blends towards the current one.
var previous := Vector2.ZERO


func load_replay(path: String) -> bool:
	replay = Replay.new()
	return replay.read_file(path)


func prepare(definition: LevelDefinition, seed_value: int) -> void:
	level = definition
	model = Route.new(seed_value, level.rules_data())
	previous = Vector2(model.x, model.y)
	_rebuild_view()


func start(definition: LevelDefinition, seed_value: int) -> void:
	clear_input()
	clock = 0.0
	replay_held = false
	paused = false
	active = true
	prepare(definition, seed_value)


func _rebuild_view() -> void:
	view.configure(level, model)
	view_ready = true


func clear_input() -> void:
	keyboard_held = false
	touch_id = -1
	pending_press = false


func set_paused(value: bool) -> void:
	paused = value
	clear_input()


func set_options(muted: bool, reduced: bool) -> void:
	sound.set_muted(muted)
	view.set_reduced(reduced)


func feed_input(event: InputEvent) -> bool:
	var pressed := false
	var key := event as InputEventKey
	var touch := event as InputEventScreenTouch
	if key and key.keycode == KEY_SPACE and not key.echo:
		pressed = key.pressed and not keyboard_held
		keyboard_held = key.pressed
	elif touch:
		if touch.pressed and touch_id == -1:
			touch_id = touch.index
			pressed = true
		elif not touch.pressed and touch.index == touch_id:
			touch_id = -1
	return pressed


func advance(delta: float, mode: String) -> void:
	if active and mode == "playing" and not paused:
		clock += delta
		while clock >= TICK and active:
			clock -= TICK
			tick()
	if view_ready:
		# Blending between ticks keeps motion smooth at any refresh rate. A pause keeps
		# the clock, so the courier stays where it was drawn.
		var blend := clampf(clock / TICK, 0.0, 1.0) if active else 1.0
		var at := previous.lerp(Vector2(model.x, model.y), blend) / 1000.0
		view.present(model, at, "result" if model.status != "running" else mode, paused, delta)


func queue_jump() -> void:
	pending_press = true


func tick() -> void:
	var pressed := pending_press
	var held := keyboard_held or touch_id >= 0
	pending_press = false
	if replay != null:
		pressed = false
		if replay.actions.has(model.tick + 1):
			held = replay.actions[model.tick + 1]
			pressed = held and not replay_held
			replay_held = held
		held = replay_held
	previous = Vector2(model.x, model.y)
	model.step(pressed, held)
	if view_ready and DisplayServer.get_name() != "headless":
		view.react(model.events, model)
		for event: String in model.events:
			sound.play(event)
	for event: String in model.events:
		event_happened.emit(event)
	if model.status != "running":
		active = false
		finished.emit(model.snapshot())
