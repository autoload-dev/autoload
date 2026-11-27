"""no-stray-entries-in-addon-module-roots: a module's root holds only its parts."""

import unittest

from tools.conventions.rules.no_stray_entries_in_addon_module_roots import (
    NoStrayEntriesInAddonModuleRoots,
)
from tools.conventions.test_support import AddonModuleTest


class NoStrayEntriesInAddonModuleRootsTest(AddonModuleTest):
    rule = NoStrayEntriesInAddonModuleRoots()

    def test_the_module_root_holds_its_files_add_ons_and_referenced_packages(
        self,
    ) -> None:
        self.module("widget")
        self.write("addons/widget/third_party/BUILD.bazel", "")
        self.write("addons/widget/tests/x/BUILD.bazel", "")
        # Packages that another package of the module or another module loads by label.
        self.write("addons/widget/shared/BUILD.bazel", 'filegroup(name = "files")\n')
        self.write("addons/widget/widget/defs.bzl", 'SHARED = "//shared:files"\n')
        self.write("addons/widget/rules/defs.bzl", "")
        self.write("addons/widget/rules/BUILD.bazel", "")
        self.write(
            "examples/addons/widget/rules.bzl",
            'load("@autoload_widget//rules:defs.bzl", "x")\n',
        )
        # A package that only names itself, and one that no label names.
        self.write("addons/widget/stray/BUILD.bazel", 'alias(actual = "//stray:x")\n')
        self.write("addons/widget/lonely/BUILD.bazel", "")
        # A directory that is no package, though a label names a package below it.
        self.write("addons/widget/misc/tools/BUILD.bazel", "")
        self.write("addons/widget/widget/tools.bzl", 'TOOLS = "//misc/tools:t"\n')
        self.write("addons/widget/notes.txt", "")
        root = "the module's root holds only its files, its add-ons, bcr/, tests/, third_party/"
        referenced = "and packages that other packages load by label"
        self.assertEqual(
            sorted(self.messages()),
            [
                f"addons/widget/lonely: {root} {referenced}",
                f"addons/widget/misc: {root} {referenced}",
                f"addons/widget/notes.txt: {root} {referenced}",
                f"addons/widget/stray: {root} {referenced}",
            ],
        )


if __name__ == "__main__":
    unittest.main()
