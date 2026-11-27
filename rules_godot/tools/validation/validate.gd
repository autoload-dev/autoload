extends SceneTree

# A unit's validation, which tools/godot_validation.py runs with --editor --script: it
# registers the closure's UIDs, loads the unit's scripts and then its scenes, and records
# every error and warning Godot reports while each one loads.
#
# It runs no project code. In the editor only tool scripts run, and the staged scripts have
# no tool annotation left, so loading compiles a script without running its static
# initializers and gives a resource's script a placeholder instead of an instance. Every
# autoload of project.godot names an empty stub Node, which Godot instantiated at startup in
# place of the autoload. Before the first file loads, each autoload gets back the path the
# GDScript analyzer types it by, so a script using it compiles and type-checks against its
# script.
#
# Everything happens here, before the scene tree starts and with it the editor's first
# filesystem scan; what the editor reports or writes from then until it quits is not
# recorded.

# Inferred: typed as GDScript, the constant loses the script's static members, whose calls
# then fail strict projects; a class_name would add a global name to every project.
@warning_ignore("inferred_declaration")
const Record = preload("record.gd")


class Recorder:
	extends Logger

	const TYPES: Array[String] = ["error", "warning", "script", "shader"]

	# The file loading now, which an error of Godot's own code belongs to.
	var current: String = ""
	# The unit's own files; an error another file of the closure reports belongs to
	# that file's unit, which validates it.
	var own: Dictionary = {}
	var findings: Dictionary = {}
	var _mutex: Mutex = Mutex.new()

	func _log_error(
		function: String,
		file: String,
		line: int,
		code: String,
		rationale: String,
		_editor_notify: bool,
		error_type: int,
		_backtraces: Array[ScriptBacktrace],
	) -> void:
		var subject: String = current
		if file.begins_with("res://"):
			if not own.has(file):
				return
			subject = file
		if subject.is_empty():
			return
		var finding: Dictionary = {
			"type": TYPES[error_type],
			"file": file,
			"line": line,
			"function": function,
			"text": rationale if rationale else code,
		}
		_mutex.lock()
		var subject_findings: Array = findings.get_or_add(subject, [])
		subject_findings.append(finding)
		_mutex.unlock()

	func _log_message(_message: String, _error: bool) -> void:
		pass


func _initialize() -> void:
	var action: Dictionary = Record.action()
	var autoloads: Dictionary = action["autoloads"]
	for autoload_name: String in autoloads:
		ProjectSettings.set_setting("autoload/" + autoload_name, autoloads[autoload_name])
	var recorder: Recorder = Recorder.new()
	var checked: Array = action["checked"]
	for path: String in checked:
		recorder.own[path] = true
	OS.add_logger(recorder)
	var uids: Dictionary = action["uids"]
	for path: String in uids:
		var uid: String = uids[path]
		var id: int = ResourceUID.text_to_id(uid)
		if not ResourceUID.has_id(id):
			ResourceUID.add_id(id, path)
	# Scripts first: an error of a script surfaces while the first file using it loads.
	for path: String in checked:
		recorder.current = path
		var _loaded: Resource = ResourceLoader.load(path)
	recorder.current = ""
	OS.remove_logger(recorder)
	Record.write(action, false, [], {"findings": recorder.findings})
	quit()
