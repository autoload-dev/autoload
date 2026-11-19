extends Node

func _ready() -> void:
	var scene := load("res://main/triangle.gltf") as PackedScene
	if scene == null:
		push_error("Imported glTF scene was not available")
		get_tree().quit(1)
		return
	var instance := scene.instantiate()
	if instance == null or instance.get_child_count() == 0:
		push_error("Imported glTF mesh was not available")
		get_tree().quit(1)
		return
	instance.free()
	print("rules_godot: imported glTF instantiated from its external buffer")
	get_tree().quit()
