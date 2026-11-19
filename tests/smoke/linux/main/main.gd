extends Node


func _ready() -> void:
	for descriptor in ["res://native/hello.gdextension", "res://native/cpp_example.gdextension"]:
		var status := GDExtensionManager.load_extension(descriptor)
		if status != GDExtensionManager.LOAD_STATUS_OK and status != GDExtensionManager.LOAD_STATUS_ALREADY_LOADED:
			push_error("Extension %s failed to load: %s" % [descriptor, status])
			get_tree().quit(1)
			return
	if not ClassDB.class_exists("BazelNode"):
		push_error("The godot-cpp extension did not register BazelNode")
		get_tree().quit(1)
		return
	var node = ClassDB.instantiate("BazelNode")
	if not node is Node:
		push_error("BazelNode is not a Godot Node")
		get_tree().quit(1)
		return
	node.free()
	var texture := load("res://main/icon.svg") as Texture2D
	if texture == null or texture.get_width() != 64:
		push_error("The imported texture is not usable in the exported pack")
		get_tree().quit(1)
		return
	print("rules_godot smoke: C ABI and godot-cpp extensions loaded, imported texture usable")
	get_tree().quit(0)
