extends Node

# Reports an error and still exits with 0, as a game with a broken script can.
func _ready() -> void:
	push_error("rules_godot run test error")
	get_tree().quit(0)
