class_name StaticInit
extends RefCounted

# A global class with a static constructor, and an inner class with its own.

const Guard = preload("res://guard/guard.gd")


class Inner:
	static var marker: int = Guard.value("static_init.gd Inner static var")

	static func _static_init() -> void:
		Guard.ran("static_init.gd Inner._static_init")


static func _static_init() -> void:
	Guard.ran("static_init.gd _static_init")


static func answer() -> int:
	return 42
