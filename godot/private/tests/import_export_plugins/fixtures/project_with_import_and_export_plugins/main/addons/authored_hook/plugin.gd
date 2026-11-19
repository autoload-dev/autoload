@tool
extends EditorPlugin

const ExportHook := preload("export_hook.gd")

var _hook := ExportHook.new()

func _enter_tree() -> void:
	add_export_plugin(_hook)

func _exit_tree() -> void:
	remove_export_plugin(_hook)
