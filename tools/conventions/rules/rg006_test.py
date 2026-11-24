"""RG006 regressions for command selection, module ownership and target existence."""

import unittest

from tools.conventions.rules.rg006 import CommandLabels, command_labels
from tools.conventions.test_support import Record, RepositoryTest

FILES = (
    "MODULE.bazel",
    "BUILD.bazel",
    "rules_godot/MODULE.bazel",
    "rules_godot/BUILD.bazel",
    "rules_godot/tools/BUILD.bazel",
    "examples/MODULE.bazel",
    "examples/BUILD.bazel",
    "examples/addons/sqlite/demo/BUILD.bazel",
    "consumers/demo/MODULE.bazel",
    "consumers/demo/android/BUILD.bazel",
)


RECORDS: list[Record] = [
    {"name": "//tools:driver", "path": "rules_godot/tools/BUILD.bazel"},
    {"name": "//:checks", "path": "examples/BUILD.bazel"},
    {
        "name": "//addons/sqlite/demo:run",
        "path": "examples/addons/sqlite/demo/BUILD.bazel",
    },
    {"name": "//android:android", "path": "consumers/demo/android/BUILD.bazel"},
]


class CommandLabelsTest(RepositoryTest):
    def test_selects_commands_not_source_or_application_arguments(self) -> None:
        self.assertEqual(
            [(3, "//projects/demo:run"), (4, "//:consumer_snippet"), (5, "//tools/docs")],
            command_labels("""
load("@autoload_rules_godot//godot:defs.bzl", "godot_run")
`bazel run //projects/demo:run -- //application:argument`
bazel build //path/to:target //docs/... //:consumer_snippet
`bazel run //tools/docs`
"""),
        )

    def test_punctuation_comments_and_continuations(self) -> None:
        self.assertEqual(
            [(1, "//tools:docs.check"), (2, "//tools:one"), (2, "//tools:two")],
            command_labels(
                "Then bazel test //tools:docs.check.\n"
                "bazel build //tools:one \\\n //tools:two # see //unrelated:comment\n"
            ),
        )

    def evaluate(
        self,
        documents: dict[str, str],
        records: list[Record],
        packages: tuple[str, ...] = (),
    ) -> list[tuple[str, int, str]]:
        for name in (*FILES, *packages, *documents):
            self.write(name, documents.get(name, ""))
        context = self.context(records=records)
        return [
            (item.location.path, item.location.line, item.message)
            for item in CommandLabels().evaluate(context)
        ]

    def test_resolves_all_command_styles_in_their_owning_module(self) -> None:
        documents = {
            "README.md": "`bazel build //:consumer_template`\n"
            "`bazel run @autoload_rules_godot//tools:driver`\n"
            "`bazel run //addons/sqlite/demo:run`",
            "rules_godot/docs/public/project-layout.md": "cd examples\n"
            "bazel run //addons/sqlite/demo:all",
            "docs/internal/development.md": "From `consumers/demo`, run\n"
            "`bazel test //android`",
            "examples/README.md": "`bazel test //:checks`",
        }
        self.assertEqual([], self.evaluate(documents, RECORDS))

    def test_missing_targets_and_packages_are_reported_at_their_line(self) -> None:
        documents = {
            "README.md": "Intro.\n`bazel run //tools:missing //missing:target`",
            "examples/README.md": "`bazel run //addons/sqlite/demo:missing`",
        }
        self.assertEqual(
            [
                (
                    "README.md",
                    2,
                    (
                        "//tools:missing: no rule 'missing' in package 'tools' of "
                        "module rules_godot"
                    ),
                ),
                (
                    "README.md",
                    2,
                    (
                        "//missing:target: expected one owning module for package "
                        "'missing', found 0"
                    ),
                ),
                (
                    "examples/README.md",
                    1,
                    (
                        "//addons/sqlite/demo:missing: no rule 'missing' in package "
                        "'addons/sqlite/demo' of module examples"
                    ),
                ),
            ],
            self.evaluate(documents, RECORDS),
        )

    def test_package_in_several_modules_is_ambiguous_from_the_root(self) -> None:
        findings = self.evaluate(
            {"README.md": "`bazel run //tools:driver`"},
            RECORDS,
            ("examples/tools/BUILD.bazel",),
        )
        self.assertEqual(1, len(findings))
        self.assertTrue(findings[0][2].endswith("found 2"))


if __name__ == "__main__":
    unittest.main()
