"""Regressions for the public/internal documentation boundary."""

import unittest

from tools.conventions.rules.rg013 import PublicDocumentationLinks
from tools.conventions.test_support import RepositoryTest


class PublicDocumentationLinksTest(RepositoryTest):
    def test_public_pages_and_readmes_cannot_link_to_internal_guides(self) -> None:
        for name, target in (
            ("docs/public/versions.md", "../internal/verification.md#engines"),
            ("README.md", "docs/internal/architecture.md"),
            ("examples/addons/demo/README.md", "../../../docs/internal/verification.md"),
            ("docs/public/api/index.md", "../../internal/api-reference.md"),
        ):
            self.write(name, f"Intro\n[Guide]({target})\n")
        findings = list(PublicDocumentationLinks().evaluate(self.context()))
        self.assertEqual(len(findings), 4)
        self.assertTrue(all(item.location.line == 2 for item in findings))
        self.assertEqual((self.tools.call_requests, self.tools.rule_requests), (0, 0))

    def test_link_forms_normalize_paths_and_report_definition_lines(self) -> None:
        self.write(
            "docs/public/usage.md",
            "[Inline](../internal/./guide.md?view=1#part)\n"
            "[Reference][guide]\n"
            '[guide]: <../internal/guide.md> "Title"\n'
            '<a href="/docs/internal/guide.md">Guide</a>\n'
            "![Image](../internal/image.png)\n"
            "[Encoded](%2e%2e/internal/guide.md)\n"
            "[Duplicate](../internal/guide.md) [Duplicate](../internal/guide.md)\n",
        )
        findings = list(PublicDocumentationLinks().evaluate(self.context()))
        self.assertEqual([item.location.line for item in findings], [1, 3, 4, 5, 6, 7])

    def test_literal_link_examples_and_comments_are_not_links(self) -> None:
        self.write(
            "README.md",
            "`[Inline](docs/internal/guide.md)`\n"
            "``[Inline with `](docs/internal/guide.md)``\n"
            "```markdown\n[Code](docs/internal/guide.md)\n```\n"
            "~~~~markdown\n[Code](docs/internal/guide.md)\n~~~\n"
            "[Still code](docs/internal/guide.md)\n~~~~\n"
            "    [Indented](docs/internal/guide.md)\n"
            "\t[Indented](docs/internal/guide.md)\n"
            '<!-- <a href="docs/internal/guide.md">Hidden</a>\n'
            "[Comment](docs/internal/guide.md) -->\n"
            "A bare attribute href=docs/internal/guide.md is not a link.\n",
        )
        self.assertEqual(list(PublicDocumentationLinks().evaluate(self.context())), [])

    def test_link_like_text_in_other_html_attributes_is_not_a_link(self) -> None:
        self.write(
            "README.md",
            '<span data-href="docs/internal/guide.md">Data</span>\n'
            "<span title='href=docs/internal/guide.md'>Title</span>\n",
        )
        self.assertEqual(list(PublicDocumentationLinks().evaluate(self.context())), [])

    def test_masking_preserves_real_links_and_their_source_lines(self) -> None:
        self.write(
            "README.md",
            "`[Literal](docs/internal/example.md)` [Real](docs/internal/one.md)\n"
            "[Real `label`](docs/internal/two.md) <!-- hidden -->\n"
            "```\n[Literal](docs/internal/example.md)\n```\n"
            "[Real](docs/internal/three.md)\n",
        )
        findings = list(PublicDocumentationLinks().evaluate(self.context()))
        self.assertEqual([item.location.line for item in findings], [1, 2, 6])

    def test_html_attributes_and_markdown_escapes(self) -> None:
        self.write(
            "README.md",
            '<a HREF="docs&#47;internal/one.md">One</a>\n'
            "<img src='docs/internal/two.png'>\n"
            "<a href=/docs/internal/three.md>Three</a>\n"
            r"[Escaped](docs\/internal/four.md)" + "\n",
        )
        findings = list(PublicDocumentationLinks().evaluate(self.context()))
        self.assertEqual([item.location.line for item in findings], [1, 2, 3, 4])

    def test_audience_navigation_and_unrelated_links_remain_valid(self) -> None:
        for name in (
            "docs/internal/design.md",
            "docs/README.md",
            "docs/public/AGENTS.md",
        ):
            self.write(name, "[Internal](/docs/internal/guide.md)\n")
        self.write(
            "docs/public/usage.md",
            "[Public](development.md)\n[Section](#internal)\n"
            "[Other directory](../internal-tools/guide.md)\n"
            "[External](https://example.org/docs/internal/guide.md)\n"
            "The internal documentation directory is `docs/internal/`.\n",
        )
        self.assertEqual(list(PublicDocumentationLinks().evaluate(self.context())), [])


if __name__ == "__main__":
    unittest.main()
