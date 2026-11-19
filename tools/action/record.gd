@tool
extends RefCounted

# The action's parameters and its result record; see tools/godot_staging.py.

const DIRECTORY: String = "res://addons/rules_godot_action/"


static func action() -> Dictionary:
	return JSON.parse_string(FileAccess.get_file_as_string(DIRECTORY + "action.json"))


# The importers probe's facts: the suffixes Godot's resource loaders recognize.
static func suffixes() -> Dictionary:
	return {"suffixes": Array(ResourceLoader.get_recognized_extensions_for_type(""))}


# Write the record of the action parameters describe under a temporary name and
# rename it, so the build tool never reads a partial record.
static func write(parameters: Dictionary, failed: bool, diagnostics: Array, facts: Dictionary) -> void:
	var record: Dictionary = {
		"operation": parameters["operation"],
		"verdict": "failure" if failed else "success",
		"diagnostics": diagnostics,
		"facts": facts,
	}
	var path: String = parameters["record"]
	var file: FileAccess = FileAccess.open(path + ".tmp", FileAccess.WRITE)
	if file == null:
		push_error("rules_godot: cannot write %s: %s" % [path, error_string(FileAccess.get_open_error())])
		return
	var _stored: bool = file.store_string(JSON.stringify(record))
	file.close()
	var _renamed: Error = DirAccess.rename_absolute(path + ".tmp", path)
