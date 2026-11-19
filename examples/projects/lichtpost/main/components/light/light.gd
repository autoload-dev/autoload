extends Node3D


func present(collected: bool, time: float) -> void:
	visible = not collected
	rotation.y = time * 1.2
