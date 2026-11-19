extends GdUnitTestSuite

const Sound = preload("res://main/components/sound/sound.tscn")


func test_muting_stops_active_cues_and_blocks_new_ones() -> void:
	var sound = auto_free(Sound.instantiate())
	add_child(sound)
	sound.play("jump")
	assert_bool(sound.voices[0].playing).is_true()
	sound.set_muted(true)
	assert_bool(sound.voices[0].playing).is_false()
	sound.play("land")
	assert_bool(sound.voices[1].playing).is_false()
	sound.set_muted(false)
	sound.play("light")
	assert_bool(sound.voices[1].playing).is_true()


func test_overlapping_cues_keep_the_first_sound_alive() -> void:
	var sound = auto_free(Sound.instantiate())
	add_child(sound)
	sound.play("group")
	sound.play("jump")
	assert_bool(sound.voices[0].playing).is_true()
	assert_bool(sound.voices[1].playing).is_true()
	sound.play("unknown")
	assert_int(sound.next_voice).is_equal(2)
