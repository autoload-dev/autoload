extends Node


func _ready() -> void:
	var version := Engine.get_version_info()
	var expect_source := "--expect-source" in OS.get_cmdline_user_args()
	var failures: Array[String] = []
	if version.major != 4 or version.minor != 8 or version.patch != 0 or not str(version.status).begins_with("beta"):
		failures.append("Expected Godot 4.8 beta")
	if not str(version.hash).begins_with("4d10419ca"):
		failures.append("Expected the pinned beta1 engine revision")
	if not ClassDB.class_exists("BazelNode"):
		failures.append("The godot-cpp extension did not register BazelNode")
	else:
		var node = ClassDB.instantiate("BazelNode")
		if node is Node:
			node.free()
		else:
			failures.append("BazelNode is not a Node")
	var has_probe := ClassDB.class_exists("BazelProbe")
	var engine_name := ""
	if has_probe != expect_source:
		failures.append("Unexpected custom-module presence")
	if has_probe:
		var probe = ClassDB.instantiate("BazelProbe")
		engine_name = probe.call("engine_name")
		if probe.call("answer") != 42 or engine_name != "Godot Engine with Bazel patch":
			failures.append("The custom module or engine patch is incorrect")
	var report := {
		"engine": version,
		"platform": OS.get_name(),
		"godot_cpp_api": "4.7",
		"cpp_node_instantiated": failures.is_empty(),
		"source_built_engine": has_probe,
		"engine_name": engine_name,
		"failures": failures,
	}
	var output := FileAccess.open("user://beta-validation.json", FileAccess.WRITE)
	if output == null:
		push_error("Cannot write mobile beta validation report")
		get_tree().quit(1)
		return
	output.store_string(JSON.stringify(report))
	output.close()
	print("rules_godot: mobile beta validation " + JSON.stringify(report))
	for failure in failures:
		push_error(failure)
	get_tree().quit(0 if failures.is_empty() else 1)
