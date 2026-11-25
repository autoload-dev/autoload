"""A repository root with what the add-on tools read, for their tests."""

import shutil
import tempfile
import unittest
from pathlib import Path

from tools.addons.modules import ROOT, SCHEMA

SCHEMA_PATH = SCHEMA.relative_to(ROOT).as_posix()


class RepositoryTestCase(unittest.TestCase):
    """A temporary root with the files the generator and the generated file start from."""

    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        # Each addon.pkl amends the schema by its path in the repository.
        files = (".bazelversion", ".bcr/rules_godot/metadata.template.json", SCHEMA_PATH)
        for name in files:
            (self.root / name).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / name, self.root / name)
        # The root module, which ignores the add-on modules it declares in its segment.
        (self.root / "MODULE.bazel").write_text(
            'module(name = "autoload_dev")\n\ninclude("//:addons.MODULE.bazel")\n'
        )
        (self.root / ".bazelignore").write_text("addons\n")
