extends GdUnitTestSuite

const Fixture = preload("res://tests/GameFixture.gd")
const Replay = preload("res://main/rules/replay.gd")


func assert_scenario(filename: String) -> void:
	var path := "res://tests/" + filename + ".json"
	var replay = Replay.new()
	assert_bool(replay.read_file(path)).is_true()
	var game = auto_free(Fixture.create(true))
	add_child(game)
	game.base_seed = replay.seed_value
	game.run.replay = replay
	game.start_run()
	while game.run.model.status == "running" and game.run.model.tick < 7200:
		game.run.tick()
	var data: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(path))
	var expected: Dictionary = data.expected
	# JSON numbers are floats, while the simulation's distances and scores are ints.
	for key in expected:
		if expected[key] is float:
			expected[key] = int(expected[key])
	assert_str(game.mode).is_equal("result")
	assert_dict(game.run.model.snapshot()).is_equal(expected)


func test_delivery_collects_all_lights_and_completes_the_route() -> void:
	assert_scenario("delivery")


func test_missing_the_first_gap_ends_the_run() -> void:
	assert_scenario("fall")


func test_hitting_a_pipe_ends_the_run() -> void:
	assert_scenario("pipe")


func test_invalid_replay_is_rejected_before_play() -> void:
	var replay = Replay.new()
	assert_bool(replay.read_file("res://tests/invalid.json")).is_false()
	assert_str(replay.error).contains("increasing ticks")


func test_missing_replay_reports_its_path() -> void:
	var replay = Replay.new()
	assert_bool(replay.read_file("res://tests/missing.json")).is_false()
	assert_str(replay.error).contains("missing.json")
