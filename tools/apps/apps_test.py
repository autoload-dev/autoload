"""Applications declare their lanes in app.pkl."""

import tempfile
import unittest
from pathlib import Path

from tools.addons.test_support import copy_schemas
from tools.apps.apps import Application, applications
from tools.pkl.evaluate import PklError


class ApplicationsTest(unittest.TestCase):
    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        copy_schemas(self.root)

    def app(self, name: str, text: str) -> None:
        path = self.root / "examples" / name / "app.pkl"
        path.parent.mkdir(parents=True)
        path.write_text(f'amends "../../tools/apps/App.pkl"\n\n{text}')

    def test_applications_name_their_lanes(self) -> None:
        self.app("game", 'lanes = List("desktop", "android")\n')
        self.app("dish", 'lanes = List("source-engine")\n')
        found = applications(self.root)
        self.assertEqual(
            (
                Application("dish", ("source-engine",)),
                Application("game", ("desktop", "android")),
            ),
            found,
        )
        self.assertEqual("//examples/game", found[1].package)

    def test_an_unknown_lane_fails(self) -> None:
        self.app("game", 'lanes = List("quality")\n')
        with self.assertRaises(PklError):
            applications(self.root)


if __name__ == "__main__":
    unittest.main()
