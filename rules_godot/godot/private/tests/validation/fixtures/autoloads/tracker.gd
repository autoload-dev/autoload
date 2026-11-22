extends Node

# A script autoload.

const Guard = preload("res://guard/guard.gd")

var events: int = 0


func _init() -> void:
	Guard.ran("tracker._init")


func _enter_tree() -> void:
	Guard.ran("tracker._enter_tree")


func _ready() -> void:
	Guard.ran("tracker._ready")


func track(event: String) -> int:
	events += 1
	return event.length()
