extends Node3D

const Primitives = preload("res://main/shared/primitives.gd")


func configure(palette: Resource) -> void:
	Primitives.apply_palette(self, palette)
