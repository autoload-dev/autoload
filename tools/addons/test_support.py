"""A repository root with what the add-on tools read, for their tests."""

import shutil
import tempfile
import unittest
from pathlib import Path

from tools.addons.modules import ROOT, SCHEMA
from tools.apps.apps import SCHEMA as APP_SCHEMA


def copy_schemas(root: Path) -> None:
    """Copy the schemas each addon.pkl and app.pkl amend to their paths below a root."""
    for schema in (SCHEMA, APP_SCHEMA):
        target = root / schema.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(schema, target)


class RepositoryTestCase(unittest.TestCase):
    """A temporary root with the files the generator and the generated file start from."""

    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        copy_schemas(self.root)
        for name in (".bazelversion", ".bcr/rules_godot/metadata.template.json"):
            (self.root / name).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / name, self.root / name)
        # The root module, which ignores the add-on modules it declares in its segment.
        (self.root / "MODULE.bazel").write_text(
            'module(name = "autoload_dev")\n\ninclude("//:addons.MODULE.bazel")\n'
        )
        (self.root / ".bazelignore").write_text("addons\n")
