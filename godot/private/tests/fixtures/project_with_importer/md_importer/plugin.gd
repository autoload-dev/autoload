@tool
extends EditorPlugin

const MarkdownImporter := preload("importer.gd")

var _importer := MarkdownImporter.new()

func _enter_tree() -> void:
	add_import_plugin(_importer)

func _exit_tree() -> void:
	remove_import_plugin(_importer)
