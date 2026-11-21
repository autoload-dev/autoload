"""gdunit_test's rejection of a test without suites."""

load("@rules_testing//lib:test_suite.bzl", "test_suite")
load("//private:gdunit_test.bzl", "validate_suites")

def _test_gdunit_test_without_suites_fails(env):
    errors = []
    validate_suites("unit_tests", [], _fail = errors.append)
    validate_suites("unit_tests", [":unit_suites"], _fail = errors.append)
    env.expect.that_collection(errors).contains_exactly([
        "unit_tests: gdunit_test requires at least one suites target",
    ])

def validation_test_suite(name):
    test_suite(
        name = name,
        basic_tests = [_test_gdunit_test_without_suites_fails],
    )
