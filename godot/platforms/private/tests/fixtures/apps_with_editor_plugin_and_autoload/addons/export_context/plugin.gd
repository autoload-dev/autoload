@tool
extends EditorPlugin

const Context := preload("export_context.gd")
var _context := Context.new()


func _enter_tree() -> void:
	add_export_plugin(_context)


func _exit_tree() -> void:
	remove_export_plugin(_context)
