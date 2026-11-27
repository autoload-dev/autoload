"""Regressions for region headers and the head that names them."""

import unittest

from tools.conventions.rules.region_headers_named_in_head import RegionHeaders, header
from tools.conventions.test_support import RepositoryTest

LEXER = header("#", "Lexer")
GRAPH = header("#", "Graph")
PYTHON = f'''"""
Static analysis.

Sections: Lexer, Graph.
"""

import re

{LEXER}

TOKEN = re.compile("x")


def tokens(text: str) -> list[str]:
    return TOKEN.findall(text)


{GRAPH}

def _edges() -> list[str]:
    return []


def graph() -> list[str]:
    return _edges()
'''
LEXER_LINE = PYTHON.splitlines().index(LEXER) + 1
GRAPH_LINE = PYTHON.splitlines().index(GRAPH) + 1


class RegionHeadersTest(RepositoryTest):
    def findings(self) -> list[tuple[str, int, str]]:
        return [
            (item.location.path, item.location.line, item.message)
            for item in RegionHeaders().evaluate(self.context())
        ]

    def test_headers_fill_their_line_to_column_80(self) -> None:
        self.assertEqual(80, len(LEXER))
        self.assertEqual(80, len(header("//", "Conversions")))
        self.assertTrue(LEXER.startswith("# ==== Lexer ="))

    def test_headers_the_head_names_pass(self) -> None:
        self.write("tools/analysis.py", PYTHON)
        head = "# The SQLite add-on's demo.\n#\n# Sections: Apps, Tests.\n\n"
        build = (
            f"{head}{header('#', 'Apps')}\n\na()\nb()\n\n{header('#', 'Tests')}\n\nc()\n"
        )
        self.write("demo/BUILD.bazel", build)
        self.write("README.md", "# ==== Not a header in Markdown ====\n")
        self.write("plain.py", '"""A module without regions."""\n\nX = 1\n')
        self.assertEqual([], self.findings())

    def test_a_header_of_another_width_or_marker_is_reported(self) -> None:
        self.write("a.py", PYTHON.replace(LEXER, "# ==== Lexer ===="))
        runtime = header("//", "Runtime")
        self.write("b.cc", f"// Sections: Runtime.\n\n{header('#', 'Runtime')}\n")
        self.assertEqual(
            [
                ("a.py", LEXER_LINE, f"write the region header as {LEXER}"),
                ("b.cc", 3, f"write the region header as {runtime}"),
            ],
            self.findings(),
        )

    def test_an_indented_header_is_reported(self) -> None:
        self.write("a.py", PYTHON.replace(GRAPH, "    " + GRAPH))
        self.assertIn(
            ("a.py", GRAPH_LINE, "a region header stands at the top level"),
            self.findings(),
        )

    def test_section_marks_of_other_forms_are_reported(self) -> None:
        self.write(
            "a.gd", "extends Node\n\n#region Moves\n#endregion\n# ----- Old -----\n"
        )
        self.assertEqual(
            [3, 4, 5],
            [line for _, line, message in self.findings() if "section" in message],
        )

    def test_marks_inside_python_strings_are_text(self) -> None:
        self.write("a.py", '"""Usage:\n# ---- Results ----\n"""\n\nX = 1\n')
        self.assertEqual([], self.findings())

    def test_region_names_may_hold_a_period(self) -> None:
        build = f"# Sections: tools.ci, Apps.\n\n{header('#', 'tools.ci')}\n\n{header('#', 'Apps')}\n"
        self.write("BUILD.bazel", build)
        self.assertEqual([], self.findings())

    def test_the_head_must_name_the_regions_in_their_order(self) -> None:
        self.write(
            "a.py", PYTHON.replace("Sections: Lexer, Graph.", "Sections: Graph, Lexer.")
        )
        self.write("b.py", PYTHON.replace("Sections: Lexer, Graph.", ""))
        self.assertEqual(
            [
                (
                    "a.py",
                    1,
                    (
                        "the head lists Graph, Lexer; the regions are: "
                        "Sections: Lexer, Graph."
                    ),
                ),
                (
                    "b.py",
                    1,
                    "name the regions in the file's head: Sections: Lexer, Graph.",
                ),
            ],
            self.findings(),
        )

    def test_a_python_region_with_one_declaration_is_reported(self) -> None:
        self.write("a.py", PYTHON.replace('TOKEN = re.compile("x")\n', ""))
        self.assertEqual(
            [
                (
                    "a.py",
                    LEXER_LINE,
                    (
                        "region Lexer declares fewer than two names; merge it into "
                        "its neighbour"
                    ),
                )
            ],
            self.findings(),
        )


if __name__ == "__main__":
    unittest.main()
