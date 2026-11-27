"""An iOS application embeds and signs the dynamic framework of a prebuilt extension, unlinked."""

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from godot.platforms.private.tests.library_composition.ios_apps import unpacked
from tools.pack.pck import pck_file_contents, pck_file_member

_FRAMEWORK = "libhello_dynamic.ios.release.framework"
_SUPPORT = "HelloDynamicSupport.framework"


class IosDynamicFrameworkTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        directory = tempfile.TemporaryDirectory()
        cls.addClassCleanup(directory.cleanup)
        cls.app, info, cls.executable = unpacked(sys.argv[1:], Path(directory.name))
        cls.pack = cls.app / (info["CFBundleExecutable"] + ".pck")

    def test_frameworks_are_embedded_and_signed(self) -> None:
        # The extension's framework and the one it loads through @rpath.
        for framework in (_FRAMEWORK, _SUPPORT):
            path = self.app / "Frameworks" / framework
            self.assertTrue(
                (path / framework.removesuffix(".framework")).is_file(), framework
            )
            subprocess.run(
                ["/usr/bin/codesign", "--verify", "--strict", str(path)], check=True
            )

    def test_executable_does_not_link_the_framework(self) -> None:
        # Godot loads the framework when it loads the extension.
        libraries = subprocess.run(
            ["/usr/bin/otool", "-L", str(self.executable)],
            stdout=subprocess.PIPE,
            text=True,
            check=True,
        ).stdout
        self.assertNotIn(_FRAMEWORK, libraries)
        self.assertNotIn(_SUPPORT, libraries)

    def test_pack_names_the_framework_for_godot_to_load(self) -> None:
        contents = pck_file_contents(self.pack, include_paths=True)
        self.assertIn(
            "res://native/hello_dynamic.gdextension", contents["extension_list"]
        )
        descriptor = pck_file_member(
            self.pack, "native/hello_dynamic.gdextension"
        ).decode()
        self.assertIn(
            f'"res://native/bin/ios.x86_64.simulator.release/{_FRAMEWORK}"', descriptor
        )
        # The application delivers the framework; the pack holds none of its files.
        self.assertEqual([path for path in contents["paths"] if ".framework" in path], [])


if __name__ == "__main__":
    unittest.main(argv=sys.argv[:1])
