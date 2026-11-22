extends Resource

# A custom resource, which Godot instantiates when it loads a resource of it: its member
# initializers, its constructor and the setters of its stored properties run.

const Guard = preload("res://guard/guard.gd")

@export var level: int = 0:
	set(value):
		Guard.ran("settings.gd level setter")
		level = value

var initialized: int = Guard.value("settings.gd member initializer")


func _init() -> void:
	Guard.ran("settings.gd _init")
