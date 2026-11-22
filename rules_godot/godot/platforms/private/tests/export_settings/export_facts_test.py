"""Check the facts Godot reports for real Android, iOS and macOS exports."""

import json
import os
import unittest
from pathlib import Path

RUNFILES = (
    Path(os.environ["TEST_SRCDIR"])
    / os.environ["TEST_WORKSPACE"]
    / "godot/platforms/private/tests/export_settings"
)
FACTS = {
    operating_system: json.loads(
        (RUNFILES / f"{operating_system}_facts.json").read_text()
    )
    for operating_system in ["android", "ios", "macos"]
}


class ExportFactsTest(unittest.TestCase):
    def test_godot_reports_every_option_of_the_exporter(self) -> None:
        # Advanced options, which the editor shows only in its advanced mode.
        for name in ["splash_screen/icon", "gesture/swipe_to_dismiss"]:
            self.assertIn(name, FACTS["android"]["options"])
        self.assertIn("privacy/file_timestamp_access_reasons", FACTS["ios"]["options"])
        self.assertIn(
            "privacy/collected_data/email_address/collected", FACTS["macos"]["options"]
        )
        self.assertIn("ios", FACTS["ios"]["features"])

    def test_godot_versions_a_project_that_sets_none(self) -> None:
        self.assertEqual(FACTS["android"]["versions"], {"version/name": "1.0.0"})


if __name__ == "__main__":
    unittest.main()
