extends Node


func _ready() -> void:
	if ClassDB.class_exists(&"PlatformProbe"):
		add_child(ClassDB.instantiate(&"PlatformProbe"))
