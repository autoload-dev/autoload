extends GdUnitTestSuite


func test_gdunit_runs_a_suite() -> void:
	assert_int(1 + 1).is_equal(2)
