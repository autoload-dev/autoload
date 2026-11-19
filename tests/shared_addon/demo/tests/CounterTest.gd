extends GdUnitTestSuite

const Consumer = preload("res://main/main.gd")

func test_consumer_uses_shared_counter() -> void:
	var consumer = Consumer.new()
	assert_int(consumer.counter.increment(3)).is_equal(3)
	consumer.free()
