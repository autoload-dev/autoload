extends Node


func _ready() -> void:
	if ProjectSettings.get_setting("application/config/name") != "Engine configuration":
		push_error("The configured start pack was not loaded")
		get_tree().quit(1)
		return
	# The selected runtime reports its own version; the editor that exported the pack may differ.
	var version: Dictionary = Engine.get_version_info()
	print("rules_godot engine configuration runtime %d.%d.%d" % [version.major, version.minor, version.patch])
	get_tree().quit(0)
