extends GdUnitTestSuite

const Counter = preload("res://addons/native_counter/counter.gd")

func test_deliberate_failure() -> void:
	var counter = Counter.new()
	assert_int(counter.increment()).is_equal(99)
