@tool
extends EditorExportPlugin

func _get_name() -> String:
	return "ExportMarker"

func _export_begin(_features: PackedStringArray, _is_debug: bool, _path: String, _flags: int) -> void:
	add_file("res://export_marker.txt", "exported".to_utf8_buffer(), false)
