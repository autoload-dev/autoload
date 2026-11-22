extends SceneTree

func _initialize() -> void:
	assert(OS.get_cmdline_user_args() == PackedStringArray(["declared value"]))
	var image = load("res://main/icon.svg")
	assert(image is Texture2D)
	assert(image.get_width() == 16)
	print("rules_godot: direct project imports and arguments OK")
	quit()
