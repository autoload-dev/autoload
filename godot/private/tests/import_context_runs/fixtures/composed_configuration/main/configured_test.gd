extends SceneTree

func _initialize() -> void:
	_verify.call_deferred()

func _verify() -> void:
	var helper := root.get_node_or_null("State")
	if helper == null or helper.marker != 17:
		push_error("Composed autoload was unavailable")
		quit(1)
		return
	var arguments := OS.get_cmdline_user_args()
	var expected_name := arguments[0] if not arguments.is_empty() else "Configured"
	if ProjectSettings.get_setting("application/config/name") != expected_name:
		push_error("Composed typed setting was not applied")
		quit(1)
		return
	if root.has_node("ImportInputState"):
		push_error("Autoload of an import input leaked into project configuration")
		quit(1)
		return
	print("rules_godot: composed settings and autoloads OK")
	quit()
