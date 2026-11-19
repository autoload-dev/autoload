extends SceneTree

## Reads a file of the directory Godot ignores without acknowledging it.


func _initialize() -> void:
	print(FileAccess.get_file_as_string("res://report/template.html"))
	quit()
