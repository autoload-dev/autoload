extends Node

func _ready() -> void:
	var theme := ThemeDB.get_project_theme()
	if theme == null or theme.default_font_size != 21:
		_fail("The project theme setting did not reach the export")
		return
	if load("res://main/icon.svg") == null:
		_fail("The imported texture is missing")
		return
	var greeting := load("res://main/hello.greeting")
	if greeting == null or greeting.get_meta("greeting") != "Hello from an import plugin":
		_fail("The importer did not convert main/hello.greeting")
		return
	var release := "%s/%s %s" % [
		ProjectSettings.get_setting("application/config/version", ""),
		ProjectSettings.get_setting("release/build_number", 0),
		ProjectSettings.get_setting_with_override("release/channel"),
	]
	if release != OS.get_cmdline_user_args()[0]:
		_fail("Expected release %s, got %s" % [OS.get_cmdline_user_args()[0], release])
		return
	print("rules_godot: release %s" % release)
	get_tree().quit()

func _fail(message: String) -> void:
	push_error(message)
	get_tree().quit(1)
