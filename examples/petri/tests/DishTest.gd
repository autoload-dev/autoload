extends GdUnitTestSuite
## The dish: pointer input, presets, pause and the mapping from the screen into the field.

const DishScene = preload("res://main/dish/dish.tscn")
const Dish = preload("res://main/dish/dish.gd")
const FIELD := Vector2(Dish.FIELD_WIDTH, Dish.FIELD_HEIGHT)


func dish():
	var instance = auto_free(DishScene.instantiate())
	add_child(instance)
	return instance


func test_covered_mapping_finds_the_field_centre_in_wider_and_taller_controls() -> void:
	var centre := Vector2(135, 240)
	assert_vector(Dish.covered_to_field(Vector2(500, 480), Vector2(1000, 960), FIELD)).is_equal_approx(centre, Vector2.ONE * 0.01)
	assert_vector(Dish.covered_to_field(Vector2(270, 600), Vector2(540, 1200), FIELD)).is_equal_approx(centre, Vector2.ONE * 0.01)
	assert_vector(Dish.covered_to_field(Vector2.ZERO, Vector2(540, 960), FIELD)).is_equal_approx(Vector2.ZERO, Vector2.ONE * 0.01)


## The number of sampled cells that hold a culture.
static func cultured_cells(field: GrayScottField) -> int:
	var count := 0
	for y in range(0, field.get_height(), 8):
		for x in range(0, field.get_width(), 8):
			if field.get_value(x, y) > 0.1:
				count += 1
	return count


func test_the_dish_opens_with_grown_cultures() -> void:
	var instance = dish()
	assert_int(cultured_cells(instance.field)).is_greater(0)
	assert_object(instance.texture).is_not_null()


func test_tap_plants_a_culture_at_the_touched_cell() -> void:
	var instance = dish()
	await get_tree().process_frame
	assert_bool(instance.size.x > 0 and instance.size.y > 0).is_true()
	instance.paused = true
	instance.clear()
	var at: Vector2 = instance.size / 2
	var press := InputEventMouseButton.new()
	press.button_index = MOUSE_BUTTON_LEFT
	press.pressed = true
	press.position = at
	instance._gui_input(press)
	var cell: Vector2 = instance.to_field(at)
	assert_float(instance.field.get_value(int(cell.x), int(cell.y))).is_greater(0.8)
	assert_float(instance.field.get_value(0, 0)).is_equal(0.0)


func test_pause_stops_the_simulation() -> void:
	var instance = dish()
	instance.paused = true
	var before: int = instance.field.checksum()
	await get_tree().process_frame
	await get_tree().process_frame
	assert_int(instance.field.checksum()).is_equal(before)
	instance.paused = false
	await get_tree().process_frame
	assert_int(instance.field.checksum()).is_not_equal(before)


func test_presets_set_the_rates() -> void:
	var instance = dish()
	instance.apply_preset(1)
	assert_int(instance.preset).is_equal(1)
	assert_float(instance.field.get_feed()).is_equal_approx(Dish.PRESETS[1].feed, 0.00001)
	assert_float(instance.field.get_kill()).is_equal_approx(Dish.PRESETS[1].kill, 0.00001)
