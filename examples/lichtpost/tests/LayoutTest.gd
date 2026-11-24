extends GdUnitTestSuite

const Fixture = preload("res://tests/GameFixture.gd")
const Interface = preload("res://main/ui/interface/interface.gd")
const RunView = preload("res://main/run/view/run_view.gd")


func test_portrait_viewport_matches_the_phone_orientation() -> void:
	var size := Vector2(
		ProjectSettings.get_setting("display/window/size/viewport_width"),
		ProjectSettings.get_setting("display/window/size/viewport_height"),
	)
	assert_bool(size.x < size.y).is_true()
	assert_int(ProjectSettings.get_setting("display/window/handheld/orientation")).is_equal(DisplayServer.SCREEN_PORTRAIT)


func test_camera_keeps_the_courier_left_and_the_route_ahead_in_view() -> void:
	var game = auto_free(Fixture.create(false, true))
	add_child(game)
	game.start_run()
	var view = game.run.view
	view.present(game.run.model, Vector2.ZERO, "playing", false, 0.0)
	var screen: Rect2 = view.get_viewport().get_visible_rect()
	var courier: Vector2 = view.camera.unproject_position(Vector3.ZERO)
	assert_float(courier.x / screen.size.x).is_equal_approx(RunView.COURIER_LEAD, 0.01)
	assert_float(1.0 - courier.y / screen.size.y).is_equal_approx(RunView.GROUND_LINE, 0.01)
	var ahead := RunView.VIEW_WIDTH * (1.0 - RunView.COURIER_LEAD) - 0.5
	assert_bool(screen.has_point(view.camera.unproject_position(Vector3(ahead, 0, 0)))).is_true()
	# The highest lights and the full jump arc stay below the HUD's share of the screen.
	var top: Vector2 = view.camera.unproject_position(Vector3(0, 4.0, 0))
	assert_float(top.y / screen.size.y).is_greater(0.25)


func test_hud_and_dialogs_fit_inside_the_portrait_viewport() -> void:
	var game = auto_free(Fixture.create())
	add_child(game)
	var ui = game.ui
	var screen: Rect2 = ui.get_viewport().get_visible_rect()
	var screens := [
		[func(): ui.show_screen("title"), ui.title],
		[func(): ui.show_screen("result"), ui.result],
		[func(): ui.show_options(false, false), ui.options],
	]
	for entry in screens:
		entry[0].call()
		await get_tree().process_frame
		for control: Control in [entry[1], ui.hud.get_node("TopBar")]:
			assert_bool(screen.encloses(control.get_global_rect())).override_failure_message("%s overflows" % control.name).is_true()


func test_safe_area_insets_use_canvas_units() -> void:
	# A 1179x2556 phone with a 177 px status/island band and a 102 px home indicator,
	# shown in a canvas stretched to 540 units wide.
	var scale := 540.0 / 1179
	var to_canvas := Transform2D.IDENTITY.scaled(Vector2(scale, scale))
	var visible := Vector2(1179, 2556) * scale
	var insets := Interface.safe_insets(Rect2(0, 177, 1179, 2556 - 177 - 102), to_canvas, visible)
	assert_vector(insets).is_equal_approx(Vector4(0, 81.07, 0, 46.72), Vector4.ONE * 0.01)
	assert_vector(Interface.safe_insets(Rect2(), to_canvas, visible)).is_equal(Vector4.ZERO)


func test_moving_the_window_lays_out_the_safe_area_again() -> void:
	# A move, also onto another screen, changes where the display's safe area lies.
	var game = auto_free(Fixture.create())
	add_child(game)
	var margin: MarginContainer = game.ui.ui_margin
	var top := margin.get_theme_constant("margin_top")
	margin.add_theme_constant_override("margin_top", top + 100)
	game.ui.notification(Node.NOTIFICATION_WM_POSITION_CHANGED)
	assert_int(margin.get_theme_constant("margin_top")).is_equal(top)
