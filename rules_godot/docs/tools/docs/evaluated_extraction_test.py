"""Exercise rejected contracts against real Bazel extraction, rather than mocks."""

import sys
import unittest
from pathlib import Path

from tools.docs.coverage import documentation_errors, parse_module


class EvaluatedExtractionTest(unittest.TestCase):
    def test_incomplete_public_contracts_are_rejected(self) -> None:
        errors = documentation_errors(
            parse_module(METADATA.read_text()), SOURCE.read_text()
        )
        expected = [
            "public_alias",
            "public_alias.data",
            "UndocumentedInfo",
            "UndocumentedInfo.payload",
            "repo",
            "repo.url",
            "extension",
            "extension.pin",
            "extension.pin.version",
            "symbolic",
            "symbolic.data",
            "scan",
            "scan.mode",
            "tiny",
            "tiny(value)",
        ]
        for location in expected:
            with self.subTest(location=location):
                self.assertIn(location + ": missing documentation", errors)


if __name__ == "__main__":
    METADATA, SOURCE = map(Path, sys.argv[1:])
    unittest.main(argv=[sys.argv[0]])
