extends Node

# rules_godot's run logger, an autoload the runner adds through override.cfg
# (tools/godot_run.py). It creates the file rules_godot/run/errors names when the
# game starts and records there every error Godot reports while the game's tree
# exists; with rules_godot/run/stop_on_error, the first error quits the game
# with status 1.


class Recorder:
	extends Logger

	const TYPES: Array[String] = ["error", "warning", "script", "shader"]

	var file: FileAccess
	var stop: bool
	var recording: bool = true
	var _mutex: Mutex = Mutex.new()
	# An error this logger causes itself reaches it again; it is not recorded.
	var _writing: bool = false

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
		var location: String = "%s:%d" % [file_name, line]
		for backtrace: ScriptBacktrace in script_backtraces:
			if backtrace.get_frame_count() > 0:
				location = "%s:%d" % [backtrace.get_frame_file(0), backtrace.get_frame_line(0)]
				break
		var entry: Dictionary = {
			"type": TYPES[error_type],
			"location": location,
			"function": function,
			"text": rationale if rationale else code,
		}
		_mutex.lock()
		if _writing or file == null or not recording:
			_mutex.unlock()
			return
		_writing = true
		var _stored: bool = file.store_line(JSON.stringify(entry))
		file.flush()
		_writing = false
		var quit: bool = stop
		stop = false
		_mutex.unlock()
		if quit:
			(Engine.get_main_loop() as SceneTree).quit.call_deferred(1)

	func _log_message(_message: String, _error: bool) -> void:
		pass

	func close() -> void:
		_mutex.lock()
		recording = false
		if file:
			file.close()
		_mutex.unlock()


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
