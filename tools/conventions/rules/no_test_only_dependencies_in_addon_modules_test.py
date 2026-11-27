"""no-test-only-dependencies-in-addon-modules: no regular dependency only tests load."""

import unittest

from tools.conventions.rules.no_test_only_dependencies_in_addon_modules import (
    NoTestOnlyDependenciesInAddonModules,
)
from tools.conventions.test_support import AddonModuleTest


class NoTestOnlyDependenciesInAddonModulesTest(AddonModuleTest):
    rule = NoTestOnlyDependenciesInAddonModules()

    def test_a_regular_dependency_is_not_loaded_by_tests_alone(self) -> None:
        self.module("widget")
        manifest = (self.root / "addons/widget/MODULE.bazel").read_text()
        self.write(
            "addons/widget/MODULE.bazel",
            manifest + 'bazel_dep(name = "rules_testing", version = "0.9.0")\n',
        )
        self.write(
            "addons/widget/tests/BUILD.bazel",
            'load("@rules_testing//lib:analysis_test.bzl", "analysis_test")\n',
        )
        self.assertEqual(
            [
                (
                    "only tests load rules_testing, which every consumer inherits: "
                    "test with it from e2e/addons/widget/"
                )
            ],
            self.messages(),
        )
        self.write(
            "addons/widget/widget/defs.bzl", 'load("@rules_testing//lib:util.bzl", "x")\n'
        )
        self.assertEqual([], self.messages())


if __name__ == "__main__":
    unittest.main()
