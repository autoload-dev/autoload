extends GdUnitTestSuite

const Counter = preload("res://addons/native_counter/counter.gd")

func test_increment_and_reset() -> void:
	var counter = Counter.new()
	assert_int(counter.increment(4)).is_equal(4)
	assert_int(counter.increment(-1)).is_equal(3)
	counter.reset()
	assert_int(counter.value()).is_equal(0)
