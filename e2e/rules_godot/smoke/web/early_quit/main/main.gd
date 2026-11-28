extends Node

# Quits with code=<n> after frames=<n> frames, 0 meaning in _ready, from its user arguments.
var _code := 0
var _frames := 0


func _ready() -> void:
	for argument: String in OS.get_cmdline_user_args():
		var parts := argument.split("=")
		if parts[0] == "code":
			_code = int(parts[1])
		elif parts[0] == "frames":
			_frames = int(parts[1])
	print("early quit after %d frames with %d" % [_frames, _code])
	if _frames == 0:
		get_tree().quit(_code)


func _process(_delta: float) -> void:
	_frames -= 1
	if _frames == 0:
		get_tree().quit(_code)
