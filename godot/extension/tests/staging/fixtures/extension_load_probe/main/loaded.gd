extends SceneTree

# Arguments: a descriptor path and whether the runtime loaded it, "true" or "false".
func _initialize() -> void:
	var arguments := OS.get_cmdline_user_args()
	var loaded := GDExtensionManager.is_extension_loaded(arguments[0])
	if str(loaded) != arguments[1]:
		push_error("Expected %s to be loaded: %s, got %s" % [arguments[0], arguments[1], loaded])
		quit(1)
		return
	quit(0)
