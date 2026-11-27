@tool
extends EditorPlugin

# Records the result of the operation action.json names, from Godot's own
# result data: per-file import validity after the first scan, the export
# platform's messages after the export, or the facts a probe reports.

# Inferred, the constant keeps the preloaded script's own type and its static members;
# typed as GDScript, each call of them is an unsafe method access, and a class_name would
# add a global name to every project the script is staged into.
@warning_ignore("inferred_declaration")
const Record = preload("record.gd")
# The type of the export plugins below; shell.gd extends it. Inferred like Record, for the
# same reason.
@warning_ignore("inferred_declaration")
const Export = preload("export.gd")
# The export plugin of each exporting operation, loaded only by that operation.
const EXPORT_PLUGINS: Dictionary[String, String] = {
	"export": "export.gd",
	"shell": "shell.gd",
	"configuration": "configuration.gd",
}

var _action: Dictionary
var _export: Export


func _enter_tree() -> void:
	_action = Record.action()
	var operation: String = _action["operation"]
	match operation:
		"import", "initialize":
			var filesystem: EditorFileSystem = EditorInterface.get_resource_filesystem()
			var _connected: int = filesystem.filesystem_changed.connect(_scanned, CONNECT_ONE_SHOT)
		"importers":
			# Deferred until every enabled plugin, before or after this one, has
			# registered its importers.
			_record_importers.call_deferred()
		"features":
			var active: Dictionary = {}
			for tag: String in _action["tags"]:
				active[tag] = OS.has_feature(tag)
			Record.write(_action, false, [], active)
		_ when operation in EXPORT_PLUGINS:
			var plugin: GDScript = load(Record.DIRECTORY + EXPORT_PLUGINS[operation])
			_export = plugin.new()
			_export.action = _action
			add_export_plugin(_export)


func _exit_tree() -> void:
	if _export:
		remove_export_plugin(_export)


func _record_importers() -> void:
	var facts: Dictionary = Record.suffixes()
	facts["importers"] = _script_importers()
	Record.write(_action, false, [], facts)


# The importers the editor-part scripts of each add-on with an importer role define,
# found by reflection: Godot lists no registered importer with its owner.
func _script_importers() -> Array[Dictionary]:
	var found: Array[Dictionary] = []
	var scripts: Dictionary = _action.get("importer_scripts", {})
	for label: String in scripts:
		for path: String in scripts[label]:
			var script: Script = load(path) as Script
			if script == null or not script.can_instantiate():
				continue
			if not ClassDB.is_parent_class(script.get_instance_base_type(), "EditorImportPlugin"):
				continue
			var importer: Object = script.call("new")
			var suffixes: PackedStringArray = []
			if importer.has_method("_get_recognized_extensions"):
				suffixes = importer.call("_get_recognized_extensions")
			found.append({"label": label, "suffixes": Array(suffixes)})
	return found


# Godot emits this after the first scan has imported every file and written
# its UID and class caches. The build tool decides which invalid files fail.
func _scanned() -> void:
	var invalid: Array[String] = []
	_invalid_imports(EditorInterface.get_resource_filesystem().get_filesystem(), invalid)
	Record.write(_action, false, [], {"invalid": invalid})


func _invalid_imports(directory: EditorFileSystemDirectory, invalid: Array[String]) -> void:
	for index: int in directory.get_file_count():
		if not directory.get_file_import_is_valid(index):
			invalid.append(directory.get_file_path(index).trim_prefix("res://"))
	for index: int in directory.get_subdir_count():
		_invalid_imports(directory.get_subdir(index), invalid)
