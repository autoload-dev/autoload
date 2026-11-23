extends Node

# Loads the godot-cpp extension, instantiates its class and an imported texture, and quits
# with 1 unless the running engine reports EXPECTED_ENGINE_VERSION, such as 4.8.0-beta1.
func _ready() -> void:
	var result := GDExtensionManager.load_extension("res://native/cpp_example.gdextension")
	if result != GDExtensionManager.LOAD_STATUS_OK and result != GDExtensionManager.LOAD_STATUS_ALREADY_LOADED:
		push_error("C++ extension load failed: %s" % result)
		get_tree().quit(1)
		return
	if not ClassDB.class_exists("BazelNode"):
		push_error("C++ extension did not register BazelNode")
		get_tree().quit(1)
		return
	var node = ClassDB.instantiate("BazelNode")
	if not node is Node:
		push_error("BazelNode is not a Godot Node")
		get_tree().quit(1)
		return
	node.free()
	var texture = load("res://main/icon.svg")
	if not texture is Texture2D or texture.get_width() == 0:
		push_error("Imported texture is invalid")
		get_tree().quit(1)
		return
	var info := Engine.get_version_info()
	var version := "%d.%d.%d" % [info["major"], info["minor"], info["patch"]]
	if info["status"] != "stable":
		version += "-" + info["status"]
	var expected := OS.get_environment("EXPECTED_ENGINE_VERSION")
	if version != expected:
		push_error("Expected engine %s, running %s" % [expected, version])
		get_tree().quit(1)
		return
	print("godot-cpp extension loaded in Godot " + version)
	get_tree().quit(0)
