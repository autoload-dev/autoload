"""The definitions the define analysis keeps in the header and in a per-file copt."""

import sys
import unittest
from pathlib import Path


class DefineAnalysisTest(unittest.TestCase):
    def test_the_header_keeps_the_definitions_the_preprocessing_reads(self) -> None:
        self.assertEqual(
            Path(sys.argv[1]).read_text().splitlines(),
            [
                "#define GODOT_DECLARES_BUILD_PROFILE 1",
                "#define HEADER_ENABLED 1",
                "#define PASTED_DISABLED 1",
                '#define MESSAGE "header_enabled"',
                "#undef NDEBUG",
            ],
        )

    def test_per_file_copt_keeps_every_definition(self) -> None:
        self.assertEqual(
            Path(sys.argv[2]).read_text().splitlines(),
            [
                "#define GODOT_DECLARES_BUILD_PROFILE 1",
                "#define HEADER_ENABLED 1",
                "#define PASTED_DISABLED 1",
                "#define COMMENT_ONLY_ENABLED 1",
                "#define INSIDE_INACTIVE_ENABLED 1",
                "#define UNUSED_ENABLED 1",
                '#define MESSAGE "header_enabled"',
                "#undef NDEBUG",
            ],
        )


if __name__ == "__main__":
    unittest.main(argv=sys.argv[:1])
