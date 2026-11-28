extends GdUnitTestSuite

func test_mock_script_class() -> void:
	var greeter: Variant = mock(Greeter)
	do_return("mocked").on(greeter).greet("web")
	assert_str(greeter.greet("web")).is_equal("mocked")

func test_spy_script_class() -> void:
	var greeter: Variant = spy(Greeter.new())
	assert_str(greeter.greet("web")).is_equal("hello web")
	verify(greeter, 1).greet("web")
