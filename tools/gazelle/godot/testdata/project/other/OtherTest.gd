extends GdUnitTestSuite

func test_body() -> void:
	assert_object(Body.new()).is_not_null()
