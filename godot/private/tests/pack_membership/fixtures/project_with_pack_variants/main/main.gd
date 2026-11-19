extends Node

const Example = preload("res://main/shared/math.gd")

func _ready() -> void:
	var brand = JSON.parse_string(FileAccess.get_file_as_string("res://main/data/brand.json"))
	var version = JSON.parse_string(FileAccess.get_file_as_string("res://main/data/version.json"))
	var level = JSON.parse_string(FileAccess.get_file_as_string("res://main/levels/one.json"))
	if version.version != 1 or level.level != 1 or Example.answer() != 42:
		push_error("Invalid shared script or dynamic raw data")
		get_tree().quit(1)
		return
	var expected := OS.get_cmdline_user_args()
	if not expected.is_empty() and brand.brand != expected[0]:
		push_error("Expected brand %s, got %s" % [expected[0], brand.brand])
		get_tree().quit(1)
		return
	print("capabilities: %s %d" % [brand.brand, Example.answer()])
	get_tree().quit()
