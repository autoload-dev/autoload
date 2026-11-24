extends GdUnitTestSuite

const Route = preload("res://main/rules/route_model.gd")
const Level = preload("res://main/levels/level_01/level_01.tres")


func test_level_01_keeps_every_frozen_layout_for_65_seeds() -> void:
	# Captured with Godot 4.7.2 from the route_model blob at 2ddd5e8, before
	# parameterization. Hash all gaps, pipes and light positions/taken flags.
	var hashes: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://tests/level_01_layout_hashes.json"))
	for seed_text in hashes:
		var model = Route.new(int(seed_text), Level.rules_data())
		var gaps := []
		for gap in model.gaps:
			gaps.append([gap.x, gap.y])
		var lights := []
		for light in model.lights:
			lights.append({"x": light.x, "y": light.y, "taken": light.taken})
		var layout := {"gaps": gaps, "pipes": model.pipes, "lights": lights}
		assert_str(JSON.stringify(layout).sha256_text()).override_failure_message("Layout changed for seed " + seed_text).is_equal(hashes[seed_text])


func test_level_01_seed_changes_keep_the_previous_wrap_behavior() -> void:
	for seed_value in [0, 27, 2147380000, 2147483647]:
		assert_int(Level.next_seed(seed_value)).is_equal((seed_value + 104729) & 0x7fffffff)
	var bounded = Level.duplicate()
	bounded.seed_min = 10
	bounded.seed_max = 20
	assert_int(bounded.initial_seed(0)).is_equal(10)
	assert_int(bounded.initial_seed(100)).is_equal(20)
	for seed_value in range(10, 21):
		assert_int(bounded.next_seed(seed_value)).is_between(10, 20)


func test_another_level_changes_content_using_only_resource_data() -> void:
	var other = Level.duplicate()
	other.speed = 45
	other.length = 180
	other.section_count = 0
	var model = Route.new(27, other.rules_data())
	for at in range(3):
		model.step(false, false)
	assert_int(model.x).is_equal(135)
	assert_str(model.status).is_equal("running")
	model.step(false, false)
	assert_int(model.x).is_equal(180)
	assert_str(model.status).is_equal("delivered")
	assert_bool(model.gaps.is_empty()).is_true()


func _flat_group(heights: PackedInt32Array):
	var definition = preload("res://main/run/level_definition.gd").new()
	var pattern = preload("res://main/run/section_pattern.gd").new()
	pattern.gap_width = 0
	pattern.gentle_gap_width = 0
	definition.patterns.append(pattern)
	definition.section_count = 1
	definition.light_offset = 0
	definition.light_spacing = 0
	definition.light_heights = heights
	var model = Route.new(27, definition.rules_data())
	for at in range(200):
		model.step(false, false)
	return model


func test_four_lights_complete_a_data_defined_group() -> void:
	var model = _flat_group(PackedInt32Array([600, 600, 600, 600]))
	assert_int(model.collected).is_equal(4)
	assert_int(model.score).is_equal(40)
	assert_int(model.chain).is_equal(1)


func test_three_of_four_lights_do_not_complete_a_data_defined_group() -> void:
	var model = _flat_group(PackedInt32Array([600, 600, 600, 3000]))
	assert_int(model.collected).is_equal(3)
	assert_int(model.chain).is_equal(0)


func test_a_section_without_lights_does_not_award_a_group_chain() -> void:
	var model = _flat_group(PackedInt32Array())
	assert_int(model.collected).is_equal(0)
	assert_int(model.chain).is_equal(0)
