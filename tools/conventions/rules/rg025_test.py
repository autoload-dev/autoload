"""Regressions for Python's reading order: helpers before their first caller."""

import unittest

from tools.conventions.context import EvidenceError
from tools.conventions.rules.rg025 import ReadingOrder
from tools.conventions.test_support import RepositoryTest


class ReadingOrderTest(RepositoryTest):
    def findings(self) -> list[tuple[str, int, str]]:
        return [
            (item.location.path, item.location.line, item.message)
            for item in ReadingOrder().evaluate(self.context())
        ]

    def test_helpers_above_their_callers_pass(self) -> None:
        self.write(
            "a.py",
            "def _helper():\n    return 1\n\n\n"
            "class Thing:\n    def run(self):\n        return _helper()\n\n\n"
            "def main():\n    return Thing().run()\n",
        )
        self.assertEqual([], self.findings())

    def test_a_helper_below_its_first_caller_is_reported(self) -> None:
        self.write(
            "a.py",
            "def main():\n    return _second() + _first()\n\n\n"
            "def _first():\n    return 1\n\n\n"
            "def other():\n    return _second()\n\n\n"
            "def _second():\n    return 2\n",
        )
        self.assertEqual(
            [
                ("a.py", 5, "move _first above its first caller, main on line 1"),
                ("a.py", 13, "move _second above its first caller, main on line 1"),
            ],
            self.findings(),
        )

    def test_a_local_of_a_definitions_name_is_no_call(self) -> None:
        self.write(
            "a.py",
            "def main(lanes):\n    devices = lanes\n    return devices\n\n\n"
            "def lanes():\n    return []\n\n\n"
            "def devices():\n    return []\n",
        )
        self.assertEqual([], self.findings())

    def test_recursion_between_definitions_passes(self) -> None:
        self.write(
            "a.py",
            "def even(n):\n    return n == 0 or odd(n - 1)\n\n\n"
            "def odd(n):\n    return n != 0 and even(n - 1)\n",
        )
        self.assertEqual([], self.findings())

    def test_other_files_are_skipped(self) -> None:
        self.write("a.bzl", "def main():\n    _helper()\n\ndef _helper():\n    pass\n")
        self.assertEqual([], self.findings())

    def test_a_module_that_does_not_parse_fails_the_audit(self) -> None:
        self.write("broken.py", "def (:\n")
        with self.assertRaisesRegex(EvidenceError, "broken.py: cannot parse as Python"):
            self.findings()


if __name__ == "__main__":
    unittest.main()
