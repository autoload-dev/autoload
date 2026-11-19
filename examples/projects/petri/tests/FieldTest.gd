extends GdUnitTestSuite
## The reaction_diffusion module's GrayScottField, as the dish relies on it.

const SIZE := 48
const CENTER := 24


func field(seed_value := 3) -> GrayScottField:
	var result := GrayScottField.new()
	result.setup(SIZE, SIZE, seed_value)
	result.seed_disc(Vector2(CENTER, CENTER), 5.0)
	return result


func test_same_seed_and_steps_give_the_same_checksum() -> void:
	var one := field()
	var two := field()
	one.step(40)
	two.step(40)
	assert_int(one.checksum()).is_equal(two.checksum())


func test_stepping_changes_the_field() -> void:
	var instance := field()
	var before := instance.checksum()
	instance.step()
	assert_int(instance.checksum()).is_not_equal(before)


func test_rates_change_the_pattern() -> void:
	var coral := field()
	coral.set_rates(0.0545, 0.062)
	var mitosis := field()
	mitosis.set_rates(0.0367, 0.0649)
	coral.step(40)
	mitosis.step(40)
	assert_int(coral.checksum()).is_not_equal(mitosis.checksum())
	assert_float(mitosis.get_feed()).is_equal_approx(0.0367, 0.00001)
	assert_float(mitosis.get_kill()).is_equal_approx(0.0649, 0.00001)


func test_seed_disc_raises_the_second_chemical_inside_the_radius_only() -> void:
	var instance := field()
	assert_float(instance.get_value(CENTER, CENTER)).is_greater(0.85)
	assert_float(instance.get_value(2, 2)).is_equal(0.0)


func test_clear_returns_to_the_empty_dish() -> void:
	var instance := field()
	instance.step(10)
	instance.clear()
	var empty := GrayScottField.new()
	empty.setup(SIZE, SIZE, 3)
	assert_int(instance.checksum()).is_equal(empty.checksum())


func test_image_paints_cultures_brighter_than_the_floor() -> void:
	var instance := field()
	var image := instance.get_image()
	assert_int(image.get_width()).is_equal(SIZE)
	assert_int(image.get_height()).is_equal(SIZE)
	assert_int(image.get_format()).is_equal(Image.FORMAT_RGBA8)
	var culture := image.get_pixel(CENTER, CENTER).get_luminance()
	var floor_color := image.get_pixel(2, 2).get_luminance()
	assert_float(culture).is_greater(floor_color)
