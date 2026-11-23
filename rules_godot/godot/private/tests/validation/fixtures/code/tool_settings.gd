@tool
extends Resource

# A custom resource that is a tool script, which the editor instantiates too.

const Guard = preload("res://guard/guard.gd")

static var marker: int = Guard.value("tool_settings.gd static var")

@export var level: int = 0:
	set(value):
		Guard.ran("tool_settings.gd level setter")
		level = value

var initialized: int = Guard.value("tool_settings.gd member initializer")


static func _static_init() -> void:
	Guard.ran("tool_settings.gd _static_init")


func _init() -> void:
	Guard.ran("tool_settings.gd _init")
