extends GdUnitTestSuite

const Route = preload("res://main/rules/route_model.gd")


func test_seed_layout_and_inputs_reproduce_the_entire_run() -> void:
	var first = Route.new(27)
	var second = Route.new(27)
	for at in range(1800):
		var press := at % 140 == 110
		var hold := at % 140 >= 110
		first.step(press, hold)
		second.step(press, hold)
		assert_dict(first.snapshot()).is_equal(second.snapshot())
	assert_array(first.gaps).is_equal(second.gaps)
	assert_array(Route.new(28).gaps).is_not_equal(first.gaps)


func test_seed_uses_more_than_the_low_bit_width_cycle() -> void:
	var layouts: Dictionary = {}
	for route_seed in range(16):
		layouts[str(Route.new(route_seed).gaps)] = true
	assert_int(layouts.size()).is_greater_equal(12)


func test_release_shortens_jump_and_holding_does_not_repeat() -> void:
	var short = Route.new()
	var high = Route.new()
	var short_peak := 0
	var high_peak := 0
	var jump_count := 0
	for at in range(65):
		short.step(at == 0, at == 0)
		high.step(at == 0, true)
		short_peak = maxi(short_peak, short.y)
		high_peak = maxi(high_peak, high.y)
		jump_count += high.events.count("jump")
	assert_int(high_peak).is_greater(short_peak + 1000)
	assert_int(jump_count).is_equal(1)
	assert_bool(high.grounded).is_true()


func test_buffered_jump_fires_on_the_tick_after_landing() -> void:
	var run = Route.new()
	run.grounded = false
	run.y = 15
	run.velocity = -20
	run.coyote = 0
	run.step(true, true)
	assert_array(run.events).contains(["land"])
	run.step(false, true)
	assert_array(run.events).contains(["jump"])
	assert_int(run.y).is_greater(0)


func test_coyote_window_allows_late_jump_but_expires() -> void:
	var late = Route.new()
	late.x = late.gaps[0].x - Route.SPEED
	late.step(false, false)
	late.step(true, true)
	assert_array(late.events).contains(["jump"])
	var missed = Route.new()
	missed.x = missed.gaps[0].x - Route.SPEED
	for at in range(8):
		missed.step(false, false)
	missed.step(true, true)
	assert_array(missed.events).not_contains(["jump"])


func test_loss_is_terminal() -> void:
	var run = Route.new()
	for at in range(300):
		run.step(false, false)
	assert_str(run.status).is_equal("lost")
	assert_str(run.reason).is_equal("fall")
	var terminal: Dictionary = run.snapshot()
	run.step(true, true)
	assert_dict(run.snapshot()).is_equal(terminal)


func test_missing_a_landing_does_not_snap_up_through_its_side() -> void:
	var run = Route.new()
	run.x = run.gaps[0].y - Route.SPEED
	run.y = -400
	run.velocity = -100
	run.grounded = false
	run.coyote = 0
	run.step(false, false)
	assert_bool(run.grounded).is_false()
	assert_int(run.y).is_less(-400)


func test_a_tap_between_ticks_still_gets_a_useful_jump() -> void:
	var run = Route.new()
	run.step(true, false)
	assert_int(run.y).is_greater(200)
	var peak: int = run.y
	for at in range(40):
		run.step(false, false)
		peak = maxi(peak, run.y)
	assert_int(peak).is_greater(Route.PIPE_HEIGHT)


func test_the_first_three_gaps_are_gentler_for_every_pattern() -> void:
	for route_seed in range(24):
		var run = Route.new(route_seed)
		for index in range(3):
			assert_int(run.gaps[index].y - run.gaps[index].x).is_less_equal(1400)
			var tap = Route.new(route_seed)
			tap.x = tap.gaps[index].x - 900
			tap.step(true, false)
			for at in range(32):
				tap.step(false, false)
			assert_str(tap.status).is_equal("running")
			assert_bool(tap.grounded).is_true()
			assert_int(tap.x).is_greater(tap.gaps[index].y)


func test_missing_a_group_resets_chain_without_ending_run() -> void:
	var run = Route.new()
	run.chain = 3
	run.x = run.gaps[0].y + 1500
	run.step(false, false)
	assert_int(run.chain).is_equal(0)
	assert_str(run.status).is_equal("running")
