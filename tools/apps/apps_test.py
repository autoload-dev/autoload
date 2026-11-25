"""Applications declare their lanes and configuration in app.pkl."""

import tempfile
import unittest
from pathlib import Path

from tools.apps.apps import ROOT, SCHEMA, Application, applications
from tools.pkl.evaluate import PklError


class ApplicationsTest(unittest.TestCase):
    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        schema = self.root / SCHEMA.relative_to(ROOT)
        schema.parent.mkdir(parents=True)
        schema.write_text(SCHEMA.read_text())

    def app(self, name: str, text: str) -> None:
        path = self.root / "examples" / name / "app.pkl"
        path.parent.mkdir(parents=True)
        path.write_text(f'amends "../../tools/apps/App.pkl"\n\n{text}')

    def test_applications_name_their_lanes_and_configuration(self) -> None:
        self.app("game", 'lanes = List("desktop", "android")\n')
        self.app("dish", 'lanes = List("source-engine")\nconfig = "dish"\n')
        self.assertEqual(
            (
                Application("dish", ("source-engine",), "dish"),
                Application("game", ("desktop", "android")),
            ),
            applications(self.root),
        )
        self.assertEqual(" --config=dish", applications(self.root)[0].flags)
        self.assertEqual("//examples/game", applications(self.root)[1].package)

    def test_an_unknown_lane_fails(self) -> None:
        self.app("game", 'lanes = List("quality")\n')
        with self.assertRaises(PklError):
            applications(self.root)


if __name__ == "__main__":
    unittest.main()
