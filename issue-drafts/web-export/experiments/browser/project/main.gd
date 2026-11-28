extends Node2D
## Prints a known log, then quits with the code the harness asks for.
## User args (after `--`): code=<int> frames=<int> lines=<int>.

var _code := 0
var _frames := 0
var _lines := 50
var _elapsed := 0


func _ready() -> void:
	for arg in OS.get_cmdline_user_args():
		var kv := arg.split("=", true, 1)
		if kv.size() != 2:
			continue
		match kv[0]:
			"code":
				_code = int(kv[1])
			"frames":
				_frames = int(kv[1])
			"lines":
				_lines = int(kv[1])
	print("ARGS ", OS.get_cmdline_args())
	print("USER_ARGS ", OS.get_cmdline_user_args())
	print("DISPLAY ", DisplayServer.get_name(), " AUDIO ", AudioServer.get_driver_name() if AudioServer.has_method("get_driver_name") else "?")
	print("ADAPTER ", RenderingServer.get_video_adapter_vendor(), " | ", RenderingServer.get_video_adapter_name(), " | ", RenderingServer.get_video_adapter_api_version())
	print("FEATURES threads=", OS.has_feature("threads"), " nothreads=", OS.has_feature("nothreads"), " debug=", OS.is_debug_build(), " web=", OS.has_feature("web"))
	print("READY code=%d frames=%d lines=%d" % [_code, _frames, _lines])
	for i in _lines:
		print("LINE %d" % i)
	printerr("ERRLINE stderr")
	if _frames == 0:
		_quit()


func _process(_delta: float) -> void:
	if _frames == 0:
		return
	_elapsed += 1
	if _elapsed == _frames:
		_quit()


func _quit() -> void:
	print("LAST after frames=%d" % _elapsed)
	get_tree().quit(_code)
