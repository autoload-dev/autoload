"""Regressions for local links in documentation and agent instructions."""

import unittest

from tools.conventions.rules.rg016 import LocalLinks
from tools.conventions.test_support import RepositoryTest


class LocalLinksTest(RepositoryTest):
    def findings(self, files: tuple[str, ...] | None = None) -> list[str]:
        return [
            f"{item.location.path}:{item.location.line}: {item.message}"
            for item in LocalLinks().evaluate(self.context(files=files))
        ]

    def test_links_to_existing_files_directories_and_anchors_pass(self) -> None:
        self.write(
            "docs/internal/guide.md",
            "# Guide\n\n## The `aspect work` task\n\n## Setup\n\n## Setup\n\n"
            '<a id="custom"></a>\n',
        )
        self.write("tools/BUILD.bazel", "")
        self.write(
            "AGENTS.md",
            "[Guide](docs/internal/guide.md#the-aspect-work-task)\n"
            "[Again](docs/internal/guide.md#setup-1) [Custom](/docs/internal/guide.md#custom)\n"
            "[Tools](tools/) [Build](tools/BUILD.bazel#L1)\n"
            "[External](https://example.org/missing.md) [Mail](mailto:someone@example.org)\n",
        )
        self.write(".agents/skills/demo/SKILL.md", "[Root](../../../AGENTS.md)\n")
        self.write("README.md", "# Intro\n\n[Self](#intro)\n")
        self.assertEqual(self.findings(), [])

    def test_missing_targets_and_anchors_are_reported_in_every_checked_file(self) -> None:
        self.write("docs/internal/guide.md", "# Guide\n")
        self.write("addons/AGENTS.md", "Intro\n[Gone](../docs/internal/gone.md)\n")
        self.write(
            ".agents/skills/demo/SKILL.md",
            "[Anchor](../../../docs/internal/guide.md#gone)\n",
        )
        self.write("rules_godot/README.md", "[Self](#nothing)\n[Out](../../outside.md)\n")
        self.assertEqual(
            self.findings(),
            [
                (
                    ".agents/skills/demo/SKILL.md:1: no heading or anchor 'gone' in "
                    "docs/internal/guide.md"
                ),
                "addons/AGENTS.md:2: link target does not exist: docs/internal/gone.md",
                (
                    "rules_godot/README.md:1: no heading or anchor 'nothing' in "
                    "rules_godot/README.md"
                ),
                "rules_godot/README.md:2: link leaves the repository: ../outside.md",
            ],
        )

    def test_code_examples_and_other_markdown_are_not_checked(self) -> None:
        self.write(
            "docs/internal/guide.md",
            "`[Inline](gone.md)`\n```markdown\n[Code](gone.md)\n```\n"
            "# Heading\n```\n# Not a heading\n```\n[Heading](#not-a-heading)\n",
        )
        self.write("tools/notes.md", "[Gone](gone.md)\n")
        self.write(".agents/skills/demo/references/upstream.md", "[Gone](gone.md)\n")
        self.assertEqual(
            self.findings(),
            [
                (
                    "docs/internal/guide.md:9: no heading or anchor 'not-a-heading' in "
                    "docs/internal/guide.md"
                ),
            ],
        )

    def test_fragments_follow_github_rendering(self) -> None:
        self.write(
            "docs/internal/guide.md",
            "## _Fast_ **builds**\n\n## Foo &amp; Bar\n\n"
            '## <a id="old"></a>Title\n\nSetup\n=====\n\nUsage\n---\n\n'
            "<!--\n## Hidden\n-->\n",
        )
        self.write(
            "AGENTS.md",
            "[A](docs/internal/guide.md#fast-builds) [B](docs/internal/guide.md#foo--bar)\n"
            "[C](docs/internal/guide.md#title) [D](docs/internal/guide.md#old)\n"
            "[E](docs/internal/guide.md#Setup) [F](docs/internal/guide.md#usage)\n"
            "[G](docs/internal/guide.md?plain=1#L5)\n"
            "[H](docs/internal/guide.md#hidden)\n",
        )
        self.assertEqual(
            self.findings(),
            ["AGENTS.md:5: no heading or anchor 'hidden' in docs/internal/guide.md"],
        )

    def test_targets_are_listed_paths_in_their_exact_case(self) -> None:
        self.write("docs/internal/guide.md", "# Guide\n")
        self.write("user.bazelrc", "")
        self.write(
            "AGENTS.md", "[Case](docs/internal/Guide.md)\n[Ignored](user.bazelrc)\n"
        )
        self.assertEqual(
            self.findings(files=tuple(sorted(self.files - {"user.bazelrc"}))),
            [
                "AGENTS.md:1: link target does not exist: docs/internal/Guide.md",
                "AGENTS.md:2: link target does not exist: user.bazelrc",
            ],
        )

    def test_one_finding_per_line_and_problem_whatever_the_fragments(self) -> None:
        self.write(
            "AGENTS.md",
            "[A](gone.md) [B](gone.md#x) [C](../x.md#a) [D](../x.md)\n[E](gone.md)\n",
        )
        self.assertEqual(
            self.findings(),
            [
                "AGENTS.md:1: link leaves the repository: ../x.md",
                "AGENTS.md:1: link target does not exist: gone.md",
                "AGENTS.md:2: link target does not exist: gone.md",
            ],
        )


if __name__ == "__main__":
    unittest.main()
