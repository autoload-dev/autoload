extends RefCounted

# Uses scripts of another unit with static initializers: one through preload, one through
# its global class.

const StaticVar = preload("res://code/static_var.gd")


func answer() -> int:
	return StaticVar.marker + StaticInit.answer()
