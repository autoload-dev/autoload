extends Node3D

const Primitives = preload("res://main/shared/primitives.gd")
const Palette = preload("res://main/shared/palette/palette.gd")


func configure(palette: Palette) -> void:
	Primitives.apply_palette(self, palette)


func set_delivered(value: bool) -> void:
	($Window as Node3D).scale = Vector3.ONE * (1.3 if value else 1.0)
