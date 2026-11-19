extends RefCounted
## Exact production scene composition; only startup, rendering and exit are suppressed.

const Game = preload("res://main/game.gd")
const Run = preload("res://main/run/run.gd")
const Scene = preload("res://main/game.tscn")
const Level = preload("res://main/levels/level_01/level_01.tres")

class Harness extends Game:
	func _ready() -> void:
		_connect_controls()
		set_process(false)


class ReplayHarness extends Harness:
	func _finish_run(_state: Dictionary) -> void:
		mode = "result"


class RunHarness extends Run:
	func _rebuild_view() -> void:
		pass


static func create(replay_mode: bool = false, with_view: bool = false):
	var instance = Scene.instantiate()
	instance.set_script(ReplayHarness if replay_mode else Harness)
	instance.level = Level
	if not with_view:
		instance.get_node("Run").set_script(RunHarness)
	return instance
