"""Check that each file of a source run's view is imported by one import unit."""

import json
import os
import tarfile
import unittest
from collections import Counter
from pathlib import Path

PACKAGE = "godot/private/tests/import_export_plugins"
ROOT = Path(os.environ["TEST_SRCDIR"]) / os.environ["TEST_WORKSPACE"]


class ImportResultsTest(unittest.TestCase):
    def test_each_file_is_imported_by_one_unit(self) -> None:
        listing = ROOT / PACKAGE / "run_imports.json"
        entries: Counter[str] = Counter()
        for result in json.loads(listing.read_text()):
            archive = ROOT / result / "import.tar"
            # A unit without importable files has an empty result, absent from runfiles.
            if archive.is_file():
                with tarfile.open(archive) as members:
                    entries.update(members.getnames())
        # The greeting's import stages the importer; only the importer's own editor part
        # imports its icon.
        self.assertIn("main/hello.greeting.import", entries)
        self.assertIn("main/addons/greeting_importer/icon.svg.import", entries)
        self.assertEqual(
            [], sorted(entry for entry, count in entries.items() if count > 1)
        )


if __name__ == "__main__":
    unittest.main()
