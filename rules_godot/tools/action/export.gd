@tool
extends EditorExportPlugin

# Records the export's result after the export platform has written and closed
# the file, before the editor shuts down. The export packs the view without
# this plugin: its files are in a .gdignore directory, and the project
# settings and project.godot it packs are those from before the plugin joined.

# Inferred: typed as GDScript, the constant loses the script's static members, whose calls
# then fail strict projects; a class_name would add a global name to every project.
@warning_ignore("inferred_declaration")
const Record = preload("record.gd")
const PLUGIN: String = Record.DIRECTORY + "plugin.cfg"

var action: Dictionary
# What a probe extending this plugin reports.
var facts: Dictionary = {}


func _get_name() -> String:
	return "rules_godot_action"


func _export_begin(_features: PackedStringArray, _is_debug: bool, _path: String, _flags: int) -> void:
	var enabled: PackedStringArray = ProjectSettings.get_setting("editor_plugins/enabled", PackedStringArray())
	var _erased: bool = enabled.erase(PLUGIN)
	if enabled.is_empty():
		ProjectSettings.clear("editor_plugins/enabled")
	else:
		ProjectSettings.set_setting("editor_plugins/enabled", enabled)


func _export_file(path: String, _type: String, _features: PackedStringArray) -> void:
	if path == "res://project.godot":
		skip()
		var project_file: String = action["project_file"]
		add_file(path, FileAccess.get_file_as_bytes(project_file), false)


func _export_end() -> void:
	var platform: EditorExportPlatform = get_export_platform()
	var diagnostics: Array[String] = []
	for index: int in platform.get_message_count():
		if platform.get_message_type(index) >= EditorExportPlatform.EXPORT_MESSAGE_WARNING:
			diagnostics.append("%s: %s" % [platform.get_message_category(index), platform.get_message_text(index)])
	var failed: bool = platform.get_worst_message_type() == EditorExportPlatform.EXPORT_MESSAGE_ERROR
	Record.write(action, failed, diagnostics, facts)
