"""Fill {NAME} templates by the placeholder, block and empty-block rules of AGENTS.md."""

import tempfile
import unittest
from pathlib import Path

from tools.template import fill


class TemplateTest(unittest.TestCase):
    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)

    def _template(self, text: str) -> Path:
        path = self.root / "page.tpl"
        path.write_text(text, encoding="utf-8")
        return path

    def test_placeholders_and_values_must_match(self) -> None:
        template = self._template("{TITLE} and {BODY}\n")
        cases = {
            "unknown placeholder": (
                {"TITLE": "t"},
                "page.tpl has the placeholders ['BODY', 'TITLE'], not ['TITLE']",
            ),
            "extra value": (
                {"TITLE": "t", "BODY": "b", "FOOTER": "f"},
                (
                    "page.tpl has the placeholders ['BODY', 'TITLE'], "
                    "not ['BODY', 'FOOTER', 'TITLE']"
                ),
            ),
        }
        for case, (values, message) in cases.items():
            with self.subTest(case):
                with self.assertRaises(ValueError) as raised:
                    fill(template, values)
                self.assertEqual(message, str(raised.exception))

    def test_empty_block_removes_its_line(self) -> None:
        template = self._template("first\n  {SPACES}  \n\t{TABS}\t\nlast\n")
        self.assertEqual("first\nlast\n", fill(template, {"SPACES": "", "TABS": ""}))

    def test_placeholder_alone_on_its_line_takes_a_block(self) -> None:
        template = self._template("before {INLINE} after\n{BLOCK}\nend\n")
        self.assertEqual(
            "before  after\n  line one\n  line two\nend\n",
            fill(template, {"INLINE": "", "BLOCK": "  line one\n  line two"}),
        )

    def test_values_and_braces_stay_as_they_are(self) -> None:
        template = self._template("{FIRST} {OTHER} {x} {1A}\n")
        self.assertEqual(
            "has {OTHER} second {x} {1A}\n",
            fill(template, {"FIRST": "has {OTHER}", "OTHER": "second"}),
        )


if __name__ == "__main__":
    unittest.main()
