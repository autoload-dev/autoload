extends GdUnitTestSuite
## The composed scene: the dish sits under the scrims and the HUD, and HUD requests reach it.

const PetriScene = preload("res://main/petri.tscn")
const DishTest = preload("res://tests/DishTest.gd")


func petri():
	var instance = auto_free(PetriScene.instantiate())
	add_child(instance)
	return instance


func test_hud_requests_reach_the_dish() -> void:
	var instance = petri()
	instance.hud.presets.get_child(2).pressed.emit()
	assert_int(instance.dish.preset).is_equal(2)
	instance.hud.pause_button.button_pressed = true
	assert_bool(instance.dish.paused).is_true()
	assert_str(instance.hud.pause_button.text).is_equal("Resume")
	instance.hud.clear_button.pressed.emit()
	assert_int(DishTest.cultured_cells(instance.dish.field)).is_equal(0)


func test_stats_name_the_field_and_the_steps() -> void:
	var instance = petri()
	var stats: String = instance.hud.stats_label.get_parsed_text()
	assert_str(stats).contains("270×480 cells")
	assert_str(stats).contains("8 steps/frame")
