extends Node

func _ready() -> void:
	var texture := load("res://main/icon.svg") as Texture2D
	if texture == null or texture.get_width() != 64:
		push_error("Imported texture was not available in the exported PCK")
		get_tree().quit(1)
		return
	print("rules_godot: exported project and imported texture OK")
	get_tree().quit()
