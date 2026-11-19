extends Node


func _ready() -> void:
	if not ClassDB.class_exists("BazelProbe"):
		push_error("The custom module of the source-built engine is missing")
		get_tree().quit(1)
		return
	var probe = ClassDB.instantiate("BazelProbe")
	print("rules_godot: BazelProbe answer %s" % probe.call("answer"))
	print("rules_godot: engine name %s" % probe.call("engine_name"))
	if probe.call("answer") != 42:
		push_error("The custom module of the source-built engine returned a wrong value")
		get_tree().quit(1)
		return
	if probe.call("engine_name") != "Godot Engine with Bazel patch":
		push_error("The engine source patch was not applied")
		get_tree().quit(1)
		return
	print("rules_godot: source-built engine custom module OK")
	get_tree().quit(0)
