extends GdUnitTestSuite
## Portrait layout and the safe-area insets, as on phones.

const PetriScene = preload("res://main/petri.tscn")
const Hud = preload("res://main/hud/hud.gd")


func test_portrait_viewport_matches_the_phone_orientation() -> void:
	var size := Vector2(
		ProjectSettings.get_setting("display/window/size/viewport_width"),
		ProjectSettings.get_setting("display/window/size/viewport_height"),
	)
	assert_bool(size.x < size.y).is_true()
	assert_int(ProjectSettings.get_setting("display/window/handheld/orientation")).is_equal(DisplayServer.SCREEN_PORTRAIT)


func test_controls_fit_inside_the_portrait_viewport() -> void:
	var petri = auto_free(PetriScene.instantiate())
	add_child(petri)
	await get_tree().process_frame
	await get_tree().process_frame
	var screen: Rect2 = petri.get_viewport().get_visible_rect()
	for path in ["Hud/Layout/Top", "Hud/Layout/Bottom"]:
		var control: Control = petri.get_node(path)
		assert_bool(screen.encloses(control.get_global_rect())).override_failure_message("%s overflows" % path).is_true()
	assert_int(petri.hud.presets.get_child_count()).is_equal(4)


func test_safe_area_insets_use_canvas_units() -> void:
	# A 1179x2556 phone with a 177 px status/island band and a 102 px home indicator,
	# shown in a canvas stretched to 540 units wide.
	var scale := 540.0 / 1179
	var to_canvas := Transform2D.IDENTITY.scaled(Vector2(scale, scale))
	var visible := Vector2(1179, 2556) * scale
	var insets := Hud.safe_insets(Rect2(0, 177, 1179, 2556 - 177 - 102), to_canvas, visible)
	assert_vector(insets).is_equal_approx(Vector4(0, 81.07, 0, 46.72), Vector4.ONE * 0.01)
	assert_vector(Hud.safe_insets(Rect2(), to_canvas, visible)).is_equal(Vector4.ZERO)
