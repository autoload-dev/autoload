"""application-tests-under-tests: an application's tests live in its tests/ package."""

import unittest

from tools.conventions.context import Call, Location
from tools.conventions.rules.application_tests_under_tests import (
    ApplicationTestsUnderTests,
)
from tools.conventions.test_support import RepositoryTest


class ApplicationTestsUnderTestsTest(RepositoryTest):
    def test_an_application_keeps_its_tests_in_tests(self) -> None:
        self.write_consumer_modules()
        self.write("examples/game/project.godot", "")
        self.write("examples/game/BUILD.bazel", "")
        self.write("examples/game/tests/BUILD.bazel", "")
        calls = tuple(
            Call(Location(path, 1), kind, frozenset({"name"}), name)
            for path, kind, name in (
                ("examples/game/BUILD.bazel", "godot_test", "starts"),
                ("examples/game/BUILD.bazel", "godot_metadata_sync", "update"),
                ("examples/game/tests/BUILD.bazel", "gdunit_test", "suites"),
            )
        )
        context = self.context(calls=calls)
        self.assertEqual(
            ["an application's tests live in examples/game/tests/: :starts"],
            [item.message for item in ApplicationTestsUnderTests().evaluate(context)],
        )


if __name__ == "__main__":
    unittest.main()
