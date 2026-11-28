extends Node

# rules_godot's run logger, an autoload that the runner (tools/source_run/run.py) adds
# through override.cfg. When the game starts, it creates the file rules_godot/run/errors
# names. It records there every error Godot reports while the game's tree exists. With
# rules_godot/run/stop_on_error, the first error quits the game with status 1.


class Recorder:
	extends Logger

	const TYPES: Array[String] = ["error", "warning", "script", "shader"]

	var file: FileAccess
	var stop: bool
	var recording: bool = true
	var _mutex: Mutex = Mutex.new()
	# An error this logger causes itself reaches it again; it is not recorded.
	var _writing: bool = false

	# Godot's Logger fixes the signature of this override.
	# @codescene(disable:"Excess Number of Function Arguments")
	func _log_error(
		function: String,
		file_name: String,
		line: int,
		code: String,
		rationale: String,
		_editor_notify: bool,
		error_type: int,
		script_backtraces: Array[ScriptBacktrace],
	) -> void:
		# Warnings are not errors.
		if not recording or error_type == ERROR_TYPE_WARNING:
			return
		var entry: Dictionary = {
			"type": TYPES[error_type],
			"location": _location(file_name, line, script_backtraces),
			"function": function,
			"text": rationale if rationale else code,
		}
		if _record(entry):
			(Engine.get_main_loop() as SceneTree).quit.call_deferred(1)

	func _log_message(_message: String, _error: bool) -> void:
		pass

	func close() -> void:
		_mutex.lock()
		recording = false
		if file:
			file.close()
		_mutex.unlock()

	# The script line that reported the error, else the engine's.
	func _location(file_name: String, line: int, script_backtraces: Array[ScriptBacktrace]) -> String:
		for backtrace: ScriptBacktrace in script_backtraces:
			if backtrace.get_frame_count() > 0:
				return "%s:%d" % [backtrace.get_frame_file(0), backtrace.get_frame_line(0)]
		return "%s:%d" % [file_name, line]

	# Write the entry to the file; return whether the game should quit. Only the
	# first recorded error quits it.
	func _record(entry: Dictionary) -> bool:
		_mutex.lock()
		if _writing or file == null or not recording:
			_mutex.unlock()
			return false
		_writing = true
		var _stored: bool = file.store_line(JSON.stringify(entry))
		file.flush()
		_writing = false
		var quit: bool = stop
		stop = false
		_mutex.unlock()
		return quit


var _recorder: Recorder = Recorder.new()


func _init() -> void:
	var path: String = ProjectSettings.get_setting("rules_godot/run/errors")
	_recorder.file = FileAccess.open(path, FileAccess.WRITE)
	_recorder.stop = ProjectSettings.get_setting("rules_godot/run/stop_on_error", false)
	OS.add_logger(_recorder)


# Godot reports what the game left behind after its tree is gone; that is not
# an error of the game's run.
func _exit_tree() -> void:
	_recorder.close()
