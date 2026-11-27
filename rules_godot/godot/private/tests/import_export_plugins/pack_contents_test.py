"""Check that a pack holds no file of an add-on's editor part and no export plugin ran."""

import os
import unittest
from pathlib import Path

from tools.pack.pck import pck_file_contents

FIXTURE = "godot/private/tests/import_export_plugins/fixtures/project_with_import_and_export_plugins"
ROOT = Path(os.environ["TEST_SRCDIR"]) / os.environ["TEST_WORKSPACE"] / FIXTURE

# The editor parts of the fixture's add-ons: one registering an export plugin and a named
# importer.
EDITOR_PARTS = ("main/addons/export_marker/", "main/addons/greeting_importer/")


class PackContentsTest(unittest.TestCase):
    def test_pack_holds_no_editor_part_file_and_no_export_plugin_ran(self) -> None:
        paths = pck_file_contents(ROOT / "pack.pck", include_paths=True)["paths"]
        self.assertEqual([path for path in paths if path.startswith(EDITOR_PARTS)], [])
        # The export plugin would add this file; no export runs it (FR-019, D29).
        self.assertNotIn("export_marker.txt", paths)


if __name__ == "__main__":
    unittest.main()
