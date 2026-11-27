import unittest

from tools.staging.files import validate_staged_paths


class StagedFilesTest(unittest.TestCase):
    def test_staging_rejects_case_and_unicode_aliases_before_copying(self) -> None:
        for paths in [
            ("A.gd", "a.gd"),
            ("Assets/a.gd", "assets/b.gd"),
            ("a", "a/b"),
            ("caf\u00e9/a.gd", "cafe\u0301/b.gd"),
        ]:
            with (
                self.subTest(paths=paths),
                self.assertRaisesRegex(ValueError, "Conflicting"),
            ):
                validate_staged_paths({path: "input" for path in paths})
        validate_staged_paths({"a/a.gd": "one", "a/b.gd": "two"})


if __name__ == "__main__":
    unittest.main()
