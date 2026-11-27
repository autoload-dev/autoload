extends SceneTree

# The importers probe's game half: the suffixes Godot's resource loaders
# recognize without the editor's importers.

# Inferred, the constant keeps the preloaded script's own type and its static members;
# typed as GDScript, each call of them is an unsafe method access, and a class_name would
# add a global name to every project the script is staged into.
@warning_ignore("inferred_declaration")
const Record = preload("record.gd")


func _init() -> void:
	Record.write(Record.action(), false, [], Record.suffixes())
	quit()
