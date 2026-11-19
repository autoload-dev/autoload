"""
Check that the pinned Godot sources declare the export hooks the engine profile reviewed.

The engine profile classifies, per Godot minor, the virtuals of EditorExportPlugin and its
bound methods that add files, libraries or native settings to an export. A pin whose
editor_export_plugin.h or .cpp declares other names fails here until
docs/internal/export-plugin-hook-inventory.md and the profile are reviewed for it.
"""

import re
import sys
import unittest

from godot.private.engine.tests import pinned_sources

SOURCES = sys.argv[1:]

_HEADER = "editor/export/editor_export_plugin.h"
_BINDINGS = "editor/export/editor_export_plugin.cpp"
_VIRTUAL = re.compile(r"^\s*GDVIRTUAL\w*\(([^)]*)\)", re.MULTILINE)
_HOOK_NAME = re.compile(r"(?<!\w)_[a-z][a-z0-9_]*")
_METHOD = re.compile(r'D_METHOD\("((?:add_[a-z0-9_]+)|skip)"')

DISPOSITIONS = {"pack", "counterpart", "none"}
OPERATING_SYSTEMS = {"android", "ios", "linux", "macos"}


def declared_hooks(header: str, bindings: str) -> set[str]:
    """The virtuals and contributing methods an EditorExportPlugin source declares."""
    virtuals = set()
    for match in _VIRTUAL.finditer(header):
        names = _HOOK_NAME.findall(match.group(1))
        if names:
            virtuals.add(names[0])
    return virtuals | set(_METHOD.findall(bindings))


def reviewed_hooks(hooks: dict) -> set[str]:
    """The method names a profile's rows cover: their names and aliases, not descriptors."""
    return {
        alias
        for name, row in hooks.items()
        if row["kind"] != "descriptor"
        for alias in [name, *row["aliases"]]
    }


class ExportHooksReviewTest(unittest.TestCase):
    def test_pinned_sources_declare_the_profile_hooks(self) -> None:
        self.assertTrue(SOURCES)
        for location in SOURCES:
            source = pinned_sources.RUNFILES / location
            version = pinned_sources.version(source)
            with self.subTest(version=version):
                files = pinned_sources.files(source, {_HEADER, _BINDINGS})
                declared = declared_hooks(
                    files[_HEADER].decode("utf-8"), files[_BINDINGS].decode("utf-8")
                )
                hooks = pinned_sources.profile(pinned_sources.minor(source))
                self.assertEqual(
                    sorted(declared),
                    sorted(reviewed_hooks(hooks["export_hooks"])),
                    f"Godot {version} declares other export hooks than the profile "
                    "reviewed; see docs/internal/export-plugin-hook-inventory.md",
                )

    def test_every_row_is_valid(self) -> None:
        for minor in ["4.7", "4.8"]:
            for name, row in pinned_sources.profile(minor)["export_hooks"].items():
                with self.subTest(minor=minor, hook=name):
                    self.assertIn(row["disposition"], DISPOSITIONS)
                    self.assertLessEqual(set(row["operating_systems"]), OPERATING_SYSTEMS)
                    pack = row["disposition"] == "pack"
                    self.assertEqual(pack, not row["operating_systems"])
                    self.assertEqual(
                        row["disposition"] == "counterpart", bool(row["counterpart"])
                    )


if __name__ == "__main__":
    unittest.main(argv=sys.argv[:1])
