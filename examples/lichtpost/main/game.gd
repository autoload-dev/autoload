extends Node
## Entry and screen flow: title -> round(level) -> result.

const LevelDefinition = preload("res://main/run/level_definition.gd")
const Run = preload("res://main/run/run.gd")
const Interface = preload("res://main/ui/interface/interface.gd")
@export var level: LevelDefinition
var mode := "title"
var paused := false
var best := 0
var base_seed := 27
var muted := false
var reduced_motion := false
var result_age := 0.0
var settings_was_paused := false
@onready var run: Run = $Run
@onready var ui: Interface = $Interface


func _ready() -> void:
	ui.fit_desktop_window()
	for argument in OS.get_cmdline_user_args():
		if argument.begins_with("--seed="):
			base_seed = level.initial_seed(int(argument.trim_prefix("--seed=")))
		if argument.begins_with("--replay="):
			if not run.load_replay(argument.trim_prefix("--replay=")):
				push_error(run.replay.error)
				get_tree().quit(2)
				return
			base_seed = run.replay.seed_value
	if run.replay == null:
		_load_settings()
	_connect_controls()
	run.set_options(muted, reduced_motion)
	run.prepare(level, base_seed)
	if run.replay != null:
		start_run()
		if DisplayServer.get_name() == "headless":
			while run.model.status == "running" and run.model.tick < 7200:
				run.tick()
			if run.model.status == "running":
				push_error("Replay exceeded 7200 ticks")
				get_tree().quit(3)
	elif DisplayServer.get_name() == "headless":
		push_error("Headless play requires --replay=<file>")
		get_tree().quit(2)


func _connect_controls() -> void:
	ui.start_requested.connect(start_run)
	ui.new_route_requested.connect(new_route)
	ui.pause_requested.connect(toggle_pause)
	ui.options_requested.connect(toggle_options)
	ui.mute_changed.connect(set_muted)
	ui.motion_changed.connect(set_reduced_motion)
	run.finished.connect(_finish_run)
	run.event_happened.connect(_on_event)


func start_run() -> void:
	mode = "playing"
	paused = false
	ui.begin_run()
	if run.replay == null:
		base_seed = level.initial_seed(base_seed)
	run.start(level, base_seed)


func new_route() -> void:
	base_seed = level.next_seed(base_seed)
	start_run()


func toggle_pause() -> void:
	if ui.options_open():
		toggle_options()
		return
	if mode != "playing" or run.replay != null:
		return
	paused = not paused
	run.set_paused(paused)
	ui.set_paused(paused)


func toggle_options() -> void:
	if not ui.options_open():
		settings_was_paused = paused
		if mode == "playing" and not paused:
			toggle_pause()
		ui.show_options(muted, reduced_motion)
	else:
		ui.show_screen(mode)
		if mode == "playing" and not settings_was_paused:
			toggle_pause()


func _notification(what: int) -> void:
	if what == NOTIFICATION_APPLICATION_FOCUS_OUT and mode == "playing" and not paused:
		toggle_pause()


func _unhandled_input(event: InputEvent) -> void:
	if run.replay != null:
		return
	var key := event as InputEventKey
	if key and key.keycode == KEY_ESCAPE and key.pressed and not key.echo:
		toggle_pause()
		return
	# Controls receive emulated mouse events; original touches cannot also jump.
	# Releases still reach the owning finger when it finishes over a control.
	var touch := event as InputEventScreenTouch
	if touch and touch.pressed and ui.contains_pointer(touch.position):
		return
	var pressed := run.feed_input(event)
	if pressed and not paused and not ui.options_open():
		if mode != "playing":
			if mode == "title" or result_age >= 0.45:
				start_run()
		else:
			run.queue_jump()


func _process(delta: float) -> void:
	if mode == "result":
		result_age += delta
	run.advance(delta, mode)
	if not paused:
		ui.advance(delta)
	if mode == "playing" and not paused:
		ui.update_run(run.model.collected, run.model.score, 1 + mini(run.model.chain, 3), run.model.x * 100.0 / run.model.route_length)


func _finish_run(state: Dictionary) -> void:
	mode = "result"
	result_age = 0.0
	best = maxi(best, state.score)
	_save_settings()
	ui.show_result(state, best, base_seed)
	if run.replay != null:
		print("LICHTPOST_RESULT " + JSON.stringify(state))
		if DisplayServer.get_name() == "headless":
			get_tree().quit(0)


func _on_event(event: String) -> void:
	if event == "group":
		ui.group_completed(1 + mini(run.model.chain, 3), reduced_motion)


func set_muted(value: bool) -> void:
	muted = value
	run.set_options(muted, reduced_motion)
	_save_settings()


func set_reduced_motion(value: bool) -> void:
	reduced_motion = value
	run.set_options(muted, reduced_motion)
	_save_settings()


func _load_settings() -> void:
	var config := ConfigFile.new()
	if config.load("user://lichtpost.cfg") == OK:
		muted = bool(config.get_value("options", "muted", false))
		reduced_motion = bool(config.get_value("options", "reduced_motion", false))
		best = int(config.get_value("score", "best", 0))


func _save_settings() -> void:
	if run.replay != null or DisplayServer.get_name() == "headless":
		return
	var config := ConfigFile.new()
	config.set_value("options", "muted", muted)
	config.set_value("options", "reduced_motion", reduced_motion)
	config.set_value("score", "best", best)
	config.save("user://lichtpost.cfg")
