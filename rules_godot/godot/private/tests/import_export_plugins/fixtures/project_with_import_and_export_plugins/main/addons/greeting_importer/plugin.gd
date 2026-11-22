@tool
extends EditorPlugin

const GreetingImporter := preload("importer.gd")

var _importer := GreetingImporter.new()

func _enter_tree() -> void:
	add_import_plugin(_importer)

func _exit_tree() -> void:
	remove_import_plugin(_importer)
	# Godot crashes while it shuts down, as a project's plugins can make it; each process
	# that stages the importer is decided by its result all the same (FR-030).
	OS.crash("greeting_importer crashes the editor at shutdown")
