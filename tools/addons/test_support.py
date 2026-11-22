"""A repository root with what the add-on tools read, for their tests."""

import shutil
import tempfile
import unittest
from pathlib import Path

from tools.addons.modules import ROOT


class RepositoryTestCase(unittest.TestCase):
    """A temporary root with the files the generator and the generated file start from."""

    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        for name in (".bazelversion", ".bcr/rules_godot/metadata.template.json"):
            (self.root / name).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / name, self.root / name)
        # The root module, which ignores the consumer modules it names here.
        (self.root / "MODULE.bazel").write_text('module(name = "autoload_rules_godot")\n')
        (self.root / ".bazelignore").write_text("addons\n")
