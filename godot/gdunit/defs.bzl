"""Run GdUnit4 test suites as Bazel tests."""

load("//godot/private:gdunit.bzl", _godot_gdunit_test = "godot_gdunit_test")

godot_gdunit_test = _godot_gdunit_test
