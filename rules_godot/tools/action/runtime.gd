extends SceneTree

# The importers probe's game half: the suffixes Godot's resource loaders
# recognize without the editor's importers.

@warning_ignore("inferred_declaration")
const Record = preload("record.gd")


func _init() -> void:
	Record.write(Record.action(), false, [], Record.suffixes())
	quit()
