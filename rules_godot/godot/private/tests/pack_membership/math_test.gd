extends SceneTree

const Example = preload("res://main/shared/math.gd")

func _initialize() -> void:
	if Example.answer() != 42:
		push_error("Shared math failed")
		quit(1)
		return
	print("math: 42")
	quit()
