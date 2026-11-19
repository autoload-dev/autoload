extends Node


func _ready() -> void:
	if ProjectSettings.get_setting("application/config/name") != "Platform selection":
		push_error("The configured start pack was not loaded")
		get_tree().quit(1)
		return
	if not OS.has_feature("arm64") and not OS.has_feature("x86_64"):
		push_error("The runtime must report its actual CPU")
		get_tree().quit(1)
		return
	print("rules_godot unified application passed")
	get_tree().quit(0)
