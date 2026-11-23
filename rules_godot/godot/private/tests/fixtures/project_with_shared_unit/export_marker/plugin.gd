@tool
extends EditorPlugin

const ExportMarker := preload("export_marker.gd")

var _marker := ExportMarker.new()

func _enter_tree() -> void:
	add_export_plugin(_marker)

func _exit_tree() -> void:
	remove_export_plugin(_marker)
