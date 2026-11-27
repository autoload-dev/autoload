extends GdUnitTestSuite

const PROBE := "res://tests/data/probe.dart"

var probe := load(PROBE)

func test_route() -> void:
	var fixture := GameFixture.new()
	var data := FileAccess.get_file_as_string("res://tests/data/route.json")
	assert_object(fixture.courier as Body).is_not_null()
	assert_str(data).is_not_empty()
