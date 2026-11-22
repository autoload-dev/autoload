extends Node

# The script of a scene autoload's root node.

const Guard = preload("res://guard/guard.gd")

var level: int = 0


func _init() -> void:
	Guard.ran("hud._init")


func _enter_tree() -> void:
	Guard.ran("hud._enter_tree")


func _ready() -> void:
	Guard.ran("hud._ready")


func show_hud(new_level: int) -> bool:
	level = new_level
	return level > 0
