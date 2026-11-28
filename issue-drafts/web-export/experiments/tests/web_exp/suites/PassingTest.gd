extends GdUnitTestSuite

func test_addition() -> void:
	assert_int(2 + 2).is_equal(4)

func test_platform_is_web() -> void:
	assert_bool(OS.has_feature("web")).is_true()

func test_expected_engine_error() -> void:
	await assert_error(func(): push_error("deliberately checked by GdUnit")).is_push_error("deliberately checked by GdUnit")

@warning_ignore("unused_parameter")
func test_parameterized(a: int, b: int, expected: int, test_parameters := [[1, 2, 3], [2, 2, 4]]) -> void:
	assert_int(a + b).is_equal(expected)
