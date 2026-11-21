"""A platform library's resources reach the iOS applications that select it, by any path."""

import argparse
import sys
import tempfile
import unittest
from pathlib import Path, PurePosixPath

from godot.platforms.private.tests.library_composition.ios_apps import (
    bundle,
    defined_symbols,
    framework_binary,
    unpacked,
)
from tools.platforms.apple_bundle import bundle_files

_ROLES = ("app_only", "base", "direct", "loadable", "source", "transitive")

_LIBRARY_NOTICE = ("composition_notice.txt", b"shared platform resource\n")

_APP_NOTICE = ("app_notice.txt", b"app-only platform resource\n")


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    for role in _ROLES:
        parser.add_argument("--" + role, nargs="+", required=True)
    return parser.parse_args(sys.argv[1:])


class IosCompositionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.args = _arguments()
        names = {_LIBRARY_NOTICE[0], _APP_NOTICE[0]}
        cls.notices = {
            role: bundle_files(
                bundle(getattr(cls.args, role)),
                lambda name: PurePosixPath(name).name in names,
            )
            for role in _ROLES
        }

    def _assert_notice(
        self, role: str, notice: tuple[str, bytes], expected: bool
    ) -> None:
        filename, content = notice
        files = self.notices[role]
        matches = [name for name in files if PurePosixPath(name).name == filename]
        self.assertEqual(len(matches), int(expected), (role, filename, matches))
        if matches:
            self.assertEqual(files[matches[0]], content, (role, filename))

    def test_application_platform_deps_link_and_bundle_the_library(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            app, _, executable = unpacked(self.args.direct, Path(directory))
            for path in ("addon_notice.txt", "composition_notice.txt"):
                self.assertTrue((app / path).exists(), path)
            symbols = defined_symbols(executable)
            extension_symbols = defined_symbols(framework_binary(app, "hello"))
        self.assertIn("rules_godot_example_controllers", symbols)
        self.assertIn("rules_godot_library_init", extension_symbols)

    def test_project_and_extension_paths_bundle_the_library_resource(self) -> None:
        for role in ("direct", "loadable", "source", "transitive"):
            with self.subTest(role=role):
                self._assert_notice(role, _LIBRARY_NOTICE, True)
                self._assert_notice(role, _APP_NOTICE, False)

    def test_application_resources_reach_only_their_application(self) -> None:
        self._assert_notice("app_only", _APP_NOTICE, True)
        self._assert_notice("app_only", _LIBRARY_NOTICE, False)

    def test_application_without_the_library_bundles_neither_resource(self) -> None:
        self._assert_notice("base", _LIBRARY_NOTICE, False)
        self._assert_notice("base", _APP_NOTICE, False)


if __name__ == "__main__":
    unittest.main(argv=sys.argv[:1])
