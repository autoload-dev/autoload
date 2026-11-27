extends SceneTree

# The importers probe's game half: the suffixes Godot's resource loaders
# recognize without the editor's importers.

# Inferred: typed as GDScript, the constant loses the script's static members, whose calls
# then fail strict projects; a class_name would add a global name to every project.
@warning_ignore("inferred_declaration")
const Record = preload("record.gd")


func _init() -> void:
	Record.write(Record.action(), false, [], Record.suffixes())
	quit()
