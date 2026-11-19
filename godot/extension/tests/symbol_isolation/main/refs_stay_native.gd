extends SceneTree

# Each extension's read() receives a Ref of its own class and reads the value set on it.
# Fails when one extension's godot-cpp runs another extension's binding code.
func _initialize() -> void:
	for probe in ["Alpha", "Beta"]:
		var value: RefCounted = ClassDB.instantiate(probe + "Value")
		value.set_value(42)
		var read: int = value.read(value)
		if read != 42:
			push_error("%sValue.read() returned %d, expected 42" % [probe, read])
			quit(1)
			return
	quit(0)
