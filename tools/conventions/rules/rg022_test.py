"""Regressions for component names in the repository's Python tooling."""

import unittest

from tools.conventions.rules.rg022 import NoComponentNames
from tools.conventions.test_support import RepositoryTest


class NoComponentNamesTest(RepositoryTest):
    def setUp(self) -> None:
        super().setUp()
        self.write("addons/widget/MODULE.bazel", "")
        self.write("examples/game/project.godot", "")

    def findings(self) -> list[str]:
        context = self.context()
        return [item.message for item in NoComponentNames().evaluate(context)]

    def test_tools_read_components_from_their_manifests(self) -> None:
        self.write(
            "tools/ci/work.py",
            '"""Each module\'s lanes."""\n'
            "# widget once needed a workaround.\n"
            'SUFFIX = ".widget"\n'
            'GLOB = "examples/*/BUILD.bazel"\n',
        )
        self.assertEqual([], self.findings())

    def test_a_component_s_name_in_a_string_is_reported(self) -> None:
        self.write(
            "tools/ci/work.py",
            'GAME = "//examples/game:app"\n'
            'MODULE = "autoload_widget"\n'
            'HELP = "such as widget"\n',
        )
        self.assertEqual(
            [
                "names the component game; read it from its manifest",
                "names the component widget; read it from its manifest",
                "names the component widget; read it from its manifest",
            ],
            self.findings(),
        )

    def test_tests_may_name_components(self) -> None:
        self.write("tools/ci/work_test.py", 'GAME = "//examples/game:app"\n')
        self.write("tools/ci/test_support.py", 'GAME = "//examples/game:app"\n')
        self.assertEqual([], self.findings())


if __name__ == "__main__":
    unittest.main()
