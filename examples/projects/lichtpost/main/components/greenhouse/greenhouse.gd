extends Node3D

const Primitives = preload("res://main/shared/primitives.gd")


func configure(palette: Resource) -> void:
	Primitives.apply_palette(self, palette)


func set_delivered(value: bool) -> void:
	$Window.scale = Vector3.ONE * (1.3 if value else 1.0)
