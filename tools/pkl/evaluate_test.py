"""The pinned Pkl CLI evaluates modules, applies their schema and rejects bad values."""

import tempfile
import unittest
from pathlib import Path

from tools.pkl.evaluate import PklError, evaluate

SCHEMA = """\
module Schema

typealias Lane = "desktop" | "android"

lanes: List<Lane>(!isEmpty)
names: List<String> = List()
"""


class EvaluateTest(unittest.TestCase):
    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        (self.root / "Schema.pkl").write_text(SCHEMA)

    def amend(self, text: str) -> Path:
        path = self.root / "value.pkl"
        path.write_text(f'amends "Schema.pkl"\n\n{text}')
        return path

    def test_a_module_evaluates_with_the_schema_s_defaults(self) -> None:
        value = evaluate(self.amend('lanes = List("desktop")\n'))
        self.assertEqual({"lanes": ["desktop"], "names": []}, value)

    def test_an_expression_evaluates_in_the_module(self) -> None:
        path = self.amend('lanes = List("desktop", "android")\n')
        self.assertEqual({"lanes": 2}, evaluate(path, 'Map("lanes", lanes.length)'))

    def test_a_value_outside_its_type_fails(self) -> None:
        with self.assertRaisesRegex(PklError, "value.pkl"):
            evaluate(self.amend('lanes = List("ios")\n'))


if __name__ == "__main__":
    unittest.main()
