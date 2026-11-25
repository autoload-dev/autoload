extends GdUnitTestSuite

const Fixture = preload("res://tests/GameFixture.gd")


func test_real_scene_composition_restarts_the_course_and_clears_effects() -> void:
	var game = auto_free(Fixture.create(false, true))
	add_child(game)
	game.start_run()
	var view = game.run.view
	var old_platform = view.course.get_child(0)
	var body_material = view.courier.get_node("Body/Torso").material_override
	assert_bool(body_material == game.level.palette.ivory).is_true()
	assert_int(view.light_nodes.size()).is_equal(game.run.model.lights.size())
	assert_bool(view.parallax.sky.texture == game.level.sky).is_true()
	view.effects.react("land", Vector3.ZERO)
	game.start_run()
	assert_bool(view.course.is_ancestor_of(old_platform)).is_false()
	assert_bool(view.effects.sparks.is_empty()).is_true()
	view.present(game.run.model, Vector2.ZERO, "playing", false, 0.02)
	await get_tree().process_frame
	assert_bool(is_instance_valid(old_platform)).is_false()


func test_view_blends_the_courier_between_ticks_without_changing_the_model() -> void:
	var game = auto_free(Fixture.create(false, true))
	add_child(game)
	game.start_run()
	game.run.tick()
	var after_tick: Dictionary = game.run.model.snapshot()
	game.run.advance(1.0 / 120.0, "playing")
	assert_dict(game.run.model.snapshot()).is_equal(after_tick)
	var halfway: float = game.run.model.x / 2000.0
	assert_float(game.run.view.courier.position.x).is_equal_approx(halfway, 0.0001)


func test_pausing_keeps_the_courier_where_it_was_drawn() -> void:
	var game = auto_free(Fixture.create(false, true))
	add_child(game)
	game.start_run()
	game.run.tick()
	game.run.advance(1.0 / 120.0, "playing")
	var drawn: float = game.run.view.courier.position.x
	game.run.set_paused(true)
	game.run.advance(0.5, "playing")
	assert_float(game.run.view.courier.position.x).is_equal_approx(drawn, 0.0001)
