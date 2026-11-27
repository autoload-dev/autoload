extends RefCounted

# Evidence that code of these fixtures ran in a validation: it replaces the validation's
# result record with a failed one and ends Godot, so the validation fails, and the build
# with it, whether the code runs before or after the result is recorded. Each kind of code
# that could run calls it.

# The rules_godot action's parameters, which name the record (tools/editor_action/action.py).
const ACTION = "res://addons/rules_godot_action/action.json"


static func ran(what: String) -> void:
	var message = "rules_godot guard: %s ran in the content validation" % what
	printerr(message)
	var action = JSON.parse_string(FileAccess.get_file_as_string(ACTION))
	if action is Dictionary:
		var record = {
			"operation": action["operation"],
			"verdict": "failure",
			"diagnostics": [message],
			"facts": {},
		}
		var file = FileAccess.open(action["record"] + ".guard", FileAccess.WRITE)
		file.store_string(JSON.stringify(record))
		file.close()
		DirAccess.rename_absolute(action["record"] + ".guard", action["record"])
	OS.kill(OS.get_process_id())


# For initializers: records the run like ran and returns a value to initialize with.
static func value(what: String) -> int:
	ran(what)
	return 0
