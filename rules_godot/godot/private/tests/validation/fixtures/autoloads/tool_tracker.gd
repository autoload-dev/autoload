@tool
extends Node

# A script autoload, which the editor would run as a tool script.

const Guard = preload("res://guard/guard.gd")

var events: int = 0


func _init() -> void:
	Guard.ran("tool_tracker._init")


func _enter_tree() -> void:
	Guard.ran("tool_tracker._enter_tree")


func _ready() -> void:
	Guard.ran("tool_tracker._ready")


func track(event: String) -> int:
	events += 1
	return event.length()
