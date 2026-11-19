@tool
extends EditorExportPlugin

func _get_name() -> String:
	return "AuthoredHook"

func _export_begin(_features: PackedStringArray, _is_debug: bool, _path: String, _flags: int) -> void:
	push_error("A plugin enabled only in the authored project.godot ran")
