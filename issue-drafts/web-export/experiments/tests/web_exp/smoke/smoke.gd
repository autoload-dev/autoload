class_name WebSmoke
extends SceneTree

## EXPERIMENT(web tests): an application test's smallest project: draw one frame, quit 0.

var _frames: int = 0


func _initialize() -> void:
	print("smoke: started on %s, display %s" % [OS.get_name(), DisplayServer.get_name()])


func _process(_delta: float) -> bool:
	_frames += 1
	if _frames == 2:
		print("smoke: drew a frame, quitting with 0")
		quit(0)
	return false
