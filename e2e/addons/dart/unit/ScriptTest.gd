extends GdUnitTestSuite

const PROBE := "res://unit/fixtures/probe.dart"
const PLAIN := "res://unit/fixtures/plain.dart"


func _probe() -> Node2D:
	var probe: Node2D = auto_free(Node2D.new())
	probe.set_script(load(PROBE))
	return probe


func test_script_describes_its_class() -> void:
	var script: Script = load(PROBE)
	assert_str(script.get_instance_base_type()).is_equal("Node2D")
	assert_bool(script.can_instantiate()).is_true()
	var probe := _probe()
	assert_bool(probe.has_method("_ready")).is_true()
	assert_bool(probe.has_method("echo")).is_true()
	assert_bool(probe.has_method("missing")).is_false()


func test_callbacks_follow_the_mixins() -> void:
	var plain: Node = auto_free(Node.new())
	plain.set_script(load(PLAIN))
	add_child(plain)
	assert_str(plain.get_script().get_instance_base_type()).is_equal("Node")
	assert_bool(plain.has_method("_ready")).is_false()
	assert_bool(plain.is_processing()).is_false()
	assert_bool(plain.is_physics_processing()).is_false()


func test_lifecycle_callbacks_run() -> void:
	var probe := _probe()
	add_child(probe)
	await get_tree().process_frame
	await get_tree().physics_frame
	await get_tree().process_frame
	var action := InputEventAction.new()
	action.action = "ui_accept"
	action.pressed = true
	get_viewport().push_input(action)
	remove_child(probe)
	var counts: Dictionary = probe.call("counts")
	assert_int(counts["readies"]).is_equal(1)
	assert_int(counts["entries"]).is_equal(1)
	assert_int(counts["exits"]).is_equal(1)
	assert_int(counts["frames"]).is_greater(0)
	assert_int(counts["physics_frames"]).is_greater(0)
	assert_array(counts["inputs"]).contains(["InputEventAction"])
	assert_bool(probe.is_processing()).is_true()
	assert_bool(probe.is_physics_processing()).is_true()
	assert_bool(probe.call("accepting")).is_false()


func test_values_cross_both_ways() -> void:
	var probe := _probe()
	for value in [null, true, 7, 1.5, "text", Vector2(1, 2), Color(0.1, 0.2, 0.3, 0.4), [1, "a"], {"k": 2}, probe]:
		assert_that(probe.call("echo", value)).is_equal(value)
	assert_that(probe.call("echo", &"name")).is_equal("name")
	assert_object(probe.call("myself")).is_same(probe)


func test_a_godot_object_has_one_script_object() -> void:
	var probe := _probe()
	assert_array(probe.call("same", probe, probe)).is_equal([true, true])
	var plain: Node = auto_free(Node.new())
	assert_array(probe.call("same", plain, plain)).is_equal([false, true])
	assert_bool(probe.call("early_is_self")).is_true()
	assert_str(probe.call("clone")).is_equal("StateError")


func test_an_ended_script_object_stops_working() -> void:
	var first := _probe()
	first.call("remember")
	first.set_script(null)
	assert_str(_probe().call("use_remembered")).is_equal("released")


func test_dart_calls_godot() -> void:
	var probe := _probe()
	var child := Node.new()
	child.name = "Child"
	probe.add_child(child)
	assert_that(probe.call("move", 3.0)).is_equal(Vector2(3, 0))
	assert_that(probe.position).is_equal(Vector2(3, 0))
	assert_str(probe.call("child_name", "Child")).is_equal("Child")
	assert_that(probe.call("child_name", "Missing")).is_null()


func test_equal_dart_functions_are_equal_callables() -> void:
	var probe := _probe()
	assert_array(probe.call("reconnect")).is_equal([true, false])
	assert_int(probe.get_signal_connection_list("visibility_changed").size()).is_equal(0)


func test_dart_function_is_a_signal_target() -> void:
	var probe := _probe()
	add_child(probe)
	probe.name = "Renamed"
	var counts: Dictionary = probe.call("counts")
	assert_int(counts["renames"]).is_equal(1)


func test_dart_microtasks_and_timers_run() -> void:
	var probe := _probe()
	probe.call("schedule")
	var counts: Dictionary = probe.call("counts")
	assert_int(counts["microtasks"]).is_equal(1)
	# The Dart timer is due after a millisecond of real time, while a headless run's frames,
	# and so await_millis, advance faster than the clock: wait frame by frame for it, for at
	# most a second of real time.
	var deadline := Time.get_ticks_msec() + 1000
	while _timers(probe) == 0 and Time.get_ticks_msec() < deadline:
		await get_tree().process_frame
	assert_int(_timers(probe)).is_equal(1)


func _timers(probe: Node2D) -> int:
	var counts: Dictionary = probe.call("counts")
	return counts["timers"]
