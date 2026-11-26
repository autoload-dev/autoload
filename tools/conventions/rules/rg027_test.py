"""Regressions for the lint of the add-on modules' Python from the root module."""

import unittest

from tools.conventions.rules.rg027 import LintedAddonPython
from tools.conventions.test_support import Record, RepositoryTest


def python(path: str, kind: str, tags: list[str]) -> Record:
    return {
        "name": f"//{path.rsplit('/', 1)[0]}:{kind}",
        "path": path,
        "kind": kind,
        "string_lists": {"tags": tags},
    }


class LintedAddonPythonTest(RepositoryTest):
    def setUp(self) -> None:
        super().setUp()
        self.write("addons/widget/MODULE.bazel", "")
        self.write("addons/widget/config/BUILD.bazel", "")
        self.write("tools/BUILD.bazel", "")
        self.write("rules_godot/MODULE.bazel", "")
        self.write("rules_godot/tools/BUILD.bazel", "")

    def findings(self, *records: Record) -> list[str]:
        context = self.context(records=list(records))
        return [item.message for item in LintedAddonPython().evaluate(context)]

    def test_python_of_an_add_on_module_carries_lint_genfiles(self) -> None:
        message = (
            " is linted from the root module, which sees an add-on module's sources only "
            'with tags = ["lint-genfiles"]'
        )
        self.assertEqual(
            ["py_library" + message, "py_test" + message],
            self.findings(
                python("addons/widget/config/BUILD.bazel", "py_library", []),
                python(
                    "addons/widget/config/BUILD.bazel", "py_binary", ["lint-genfiles"]
                ),
                python("addons/widget/config/BUILD.bazel", "py_test", ["manual"]),
            ),
        )

    def test_other_targets_and_modules_need_no_tag(self) -> None:
        self.assertEqual(
            [],
            self.findings(
                python("addons/widget/config/BUILD.bazel", "filegroup", []),
                python("tools/BUILD.bazel", "py_library", []),
                python("rules_godot/tools/BUILD.bazel", "py_binary", []),
            ),
        )


if __name__ == "__main__":
    unittest.main()
