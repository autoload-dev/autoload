"""A repository root with what the add-on tools read, for their tests."""

import shutil
import tempfile
import unittest
from pathlib import Path

from tools.addons.modules import ROOT


class RepositoryTestCase(unittest.TestCase):
    """A temporary root with the files the generator and the generated files start from."""

    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        for name in (".bazelversion", ".bcr/metadata.template.json", "addons/README.md"):
            (self.root / name).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / name, self.root / name)
