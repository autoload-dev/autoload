extends GdUnitTestSuite

func test_deliberate_failure() -> void:
	assert_int(2 + 2).is_equal(5)

func test_passes_beside_failure() -> void:
	assert_str("web").is_equal("web")
