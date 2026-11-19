extends GdUnitTestSuite

const Fixture = preload("res://tests/GameFixture.gd")
const Route = preload("res://main/rules/route_model.gd")

func game():
	var instance = auto_free(Fixture.create())
	add_child(instance)
	instance.start_run()
	return instance


func button(instance, name: String) -> BaseButton:
	return instance.ui.find_child(name, true, false)


func touch(instance, at: Vector2, pressed: bool, finger: int = 0) -> void:
	var event := InputEventScreenTouch.new()
	event.index = finger
	event.position = at
	event.pressed = pressed
	instance._unhandled_input(event)
	if finger != 0:
		return
	# Feed Godot's emulated mouse path explicitly: headless has no operating system transport.
	var mouse := InputEventMouseButton.new()
	mouse.button_index = MOUSE_BUTTON_LEFT
	mouse.position = at
	mouse.global_position = at
	mouse.pressed = pressed
	instance.get_viewport().push_input(mouse, true)


func test_touch_pause_never_enters_the_jump_path() -> void:
	var instance = game()
	await get_tree().process_frame
	var at: Vector2 = button(instance, "PauseButton").get_global_rect().get_center()
	var count := [0]
	button(instance, "PauseButton").pressed.connect(func(): count[0] += 1)
	touch(instance, at, true)
	instance.run.tick()
	assert_int(instance.run.model.y).is_equal(0)
	touch(instance, at, false)
	assert_bool(instance.paused).is_true()
	assert_bool(instance.run.pending_press).is_false()
	assert_int(instance.run.touch_id).is_equal(-1)
	assert_int(count[0]).is_equal(1)


func test_touch_new_route_waits_for_release_and_changes_seed() -> void:
	var instance = game()
	instance.run.model.finish("lost", "fall")
	instance._finish_run(instance.run.model.snapshot())
	await get_tree().process_frame
	var at: Vector2 = button(instance, "NewRouteButton").get_global_rect().get_center()
	var count := [0]
	button(instance, "NewRouteButton").pressed.connect(func(): count[0] += 1)
	touch(instance, at, true)
	assert_str(instance.mode).is_equal("result")
	touch(instance, at, false)
	assert_int(instance.base_seed).is_not_equal(27)
	assert_int(instance.run.model.seed_value).is_equal(instance.base_seed)
	assert_str(instance.mode).is_equal("playing")
	assert_int(count[0]).is_equal(1)


func test_keyboard_and_playfield_touch_feed_identical_actions() -> void:
	var keyboard = game()
	var screen = game()
	var key := InputEventKey.new()
	key.keycode = KEY_SPACE
	key.pressed = true
	keyboard._unhandled_input(key)
	touch(screen, Vector2(20, 200), true)
	for at in range(8):
		keyboard.run.tick()
		screen.run.tick()
		assert_dict(screen.run.model.snapshot()).is_equal(keyboard.run.model.snapshot())
	key.pressed = false
	keyboard._unhandled_input(key)
	touch(screen, Vector2(20, 200), false)
	keyboard.run.tick()
	screen.run.tick()
	assert_dict(screen.run.model.snapshot()).is_equal(keyboard.run.model.snapshot())


func test_same_frame_tap_matches_a_one_tick_replay_hold() -> void:
	var live = Route.new()
	var replay = Route.new()
	live.step(true, false)
	replay.step(true, true)
	assert_dict(live.snapshot()).is_equal(replay.snapshot())


func test_playfield_hold_is_higher_than_tap_and_second_finger_is_ignored() -> void:
	var high = game()
	var short = game()
	touch(high, Vector2(20, 200), true)
	touch(short, Vector2(20, 200), true)
	high.run.tick()
	short.run.tick()
	touch(short, Vector2(20, 200), false)
	var high_peak := 0
	var short_peak := 0
	var jumps := 1
	for at in range(65):
		if at == 2:
			touch(high, Vector2(40, 200), true, 1)
		if at == 3:
			touch(high, Vector2(40, 200), false, 1)
		high.run.tick()
		short.run.tick()
		jumps += high.run.model.events.count("jump")
		high_peak = maxi(high_peak, high.run.model.y)
		short_peak = maxi(short_peak, short.run.model.y)
	assert_int(high_peak).is_greater(short_peak + 1000)
	assert_int(jumps).is_equal(1)
	high.run.model.finish("lost", "fall")
	high._finish_run(high.run.model.snapshot())
	touch(high, Vector2(40, 200), true, 1)
	assert_str(high.mode).is_equal("result")


func test_each_touch_button_fires_once_and_a_playfield_release_never_sticks() -> void:
	var instance = game()
	instance.mode = "title"
	instance.ui.show_screen("title")
	await get_tree().process_frame
	var count := [0]
	button(instance, "StartButton").pressed.connect(func(): count[0] += 1)
	var at: Vector2 = button(instance, "StartButton").get_global_rect().get_center()
	touch(instance, at, true)
	touch(instance, at, false)
	assert_int(count[0]).is_equal(1)
	assert_str(instance.mode).is_equal("playing")
	touch(instance, Vector2(20, 200), true)
	instance.run.tick()
	# A playfield gesture released over a button must still release the jump.
	touch(instance, button(instance, "PauseButton").get_global_rect().get_center(), false)
	assert_int(instance.run.touch_id).is_equal(-1)


func test_options_pause_without_consuming_ticks_and_restore_previous_pause() -> void:
	var instance = game()
	instance.run.pending_press = true
	instance.toggle_options()
	var before: Dictionary = instance.run.model.snapshot()
	instance._process(1.0)
	assert_dict(instance.run.model.snapshot()).is_equal(before)
	assert_bool(instance.paused).is_true()
	assert_bool(instance.run.pending_press).is_false()
	instance.toggle_options()
	assert_bool(instance.paused).is_false()
	assert_bool(instance.ui.find_child("TitleDialog", true, false).visible).is_false()
	instance.toggle_pause()
	instance.toggle_options()
	instance.toggle_options()
	assert_bool(instance.paused).is_true()
	assert_str(button(instance, "PauseButton").text).is_equal("Resume")


func test_touch_options_and_toggles_never_queue_a_jump() -> void:
	var instance = game()
	await get_tree().process_frame
	var at: Vector2 = button(instance, "OptionsButton").get_global_rect().get_center()
	touch(instance, at, true)
	touch(instance, at, false)
	assert_bool(instance.ui.options_open()).is_true()
	await get_tree().process_frame
	at = button(instance, "MotionToggle").get_global_rect().get_center()
	touch(instance, at, true)
	touch(instance, at, false)
	assert_bool(instance.reduced_motion).is_true()
	assert_bool(instance.run.pending_press).is_false()
	assert_int(instance.run.touch_id).is_equal(-1)
	at = button(instance, "MuteToggle").get_global_rect().get_center()
	touch(instance, at, true)
	touch(instance, at, false)
	assert_bool(instance.muted).is_true()
	at = button(instance, "BackButton").get_global_rect().get_center()
	touch(instance, at, true)
	touch(instance, at, false)
	assert_bool(instance.ui.options_open()).is_false()
	assert_bool(instance.paused).is_false()
	assert_bool(instance.run.pending_press).is_false()


func test_touch_retry_in_the_result_scene_waits_for_release_without_jumping() -> void:
	var instance = game()
	instance.run.model.finish("lost", "fall")
	instance._finish_run(instance.run.model.snapshot())
	await get_tree().process_frame
	var at: Vector2 = button(instance, "RetryButton").get_global_rect().get_center()
	touch(instance, at, true)
	assert_str(instance.mode).is_equal("result")
	touch(instance, at, false)
	assert_str(instance.mode).is_equal("playing")
	assert_bool(instance.run.pending_press).is_false()
	assert_int(instance.run.model.tick).is_equal(0)


func test_motion_and_audio_options_do_not_change_gameplay() -> void:
	var normal = game()
	var quiet = game()
	quiet.set_muted(true)
	quiet.set_reduced_motion(true)
	for at in range(180):
		normal.run.pending_press = at == 140
		quiet.run.pending_press = at == 140
		normal.run.tick()
		quiet.run.tick()
		assert_dict(quiet.run.model.snapshot()).is_equal(normal.run.model.snapshot())


func test_result_playfield_press_has_a_short_guard_against_accidental_retry() -> void:
	var instance = game()
	instance.run.model.finish("lost", "fall")
	instance._finish_run(instance.run.model.snapshot())
	touch(instance, Vector2(20, 200), true)
	assert_str(instance.mode).is_equal("result")
	touch(instance, Vector2(20, 200), false)
	instance.result_age = 0.5
	touch(instance, Vector2(20, 200), true)
	assert_str(instance.mode).is_equal("playing")


func test_palette_is_shared_but_unshaded_pickups_cannot_change_orange_geometry() -> void:
	var scene = preload("res://main/components/courier/courier.tscn")
	var first = auto_free(scene.instantiate())
	var second = auto_free(scene.instantiate())
	var light = auto_free(preload("res://main/components/light/light.tscn").instantiate())
	var body_material = first.get_node("Body/Torso").material_override
	assert_bool(body_material == second.get_node("Body/Torso").material_override).is_true()
	assert_bool(body_material == light.get_node("Mote").material_override).is_false()
	assert_int(body_material.shading_mode).is_equal(BaseMaterial3D.SHADING_MODE_PER_PIXEL)
	assert_int(light.get_node("Mote").material_override.shading_mode).is_equal(BaseMaterial3D.SHADING_MODE_UNSHADED)
