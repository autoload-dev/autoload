"""Which changes reach the source-engine tests, which the Source engine workflow runs on."""

import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tools.ci.source_engine_changes import (
    ENGINE_PATHS,
    changes_registrations,
    reaching,
    watched,
)

# A Git that reads no user or system configuration, such as signing or hooks.
GIT_ENVIRONMENT = {
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_NOSYSTEM": "1",
}


class SourceEngineChangesTest(unittest.TestCase):
    def setUp(self) -> None:
        environment = mock.patch.dict(os.environ, GIT_ENVIRONMENT)
        environment.start()
        self.addCleanup(environment.stop)
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        subprocess.run(["git", "init", "-q"], cwd=self.root, check=True)
        for path in ENGINE_PATHS:
            self.write(path + "BUILD.bazel" if path.endswith("/") else path)

    def write(self, path: str, text: str = "") -> None:
        (self.root / path).parent.mkdir(parents=True, exist_ok=True)
        (self.root / path).write_text(text)
        subprocess.run(["git", "add", path], cwd=self.root, check=True)

    def test_engine_recipes_repositories_and_their_tools_reach_the_tests(self) -> None:
        self.assertEqual(
            [
                "rules_godot/tools/engine/pin.py",
                "examples/engines/simulation/a.lock.json",
            ],
            reaching(
                [
                    "rules_godot/tools/engine/pin.py",
                    "examples/engines/simulation/a.lock.json",
                    "rules_godot/godot/app.bzl",
                ],
                watched(self.root),
            ),
        )

    def test_a_package_with_a_source_engine_test_reaches_them_with_its_subpackages(
        self,
    ) -> None:
        self.write("examples/petri/BUILD.bazel", 'tags = ["source_engine"]\n')
        self.write("examples/plain/BUILD.bazel", 'tags = ["android"]\n')
        self.assertEqual(
            ["examples/petri/main.gd", "examples/petri/tests/a.gd"],
            reaching(
                [
                    "examples/petri/main.gd",
                    "examples/petri/tests/a.gd",
                    "examples/petri_dish/main.gd",
                    "examples/plain/main.gd",
                ],
                watched(self.root),
            ),
        )

    def test_a_module_file_reaches_them_where_it_registers_engines(self) -> None:
        def diff(*lines: str) -> str:
            return "\n".join(
                (
                    "diff --git a/MODULE.bazel b/MODULE.bazel",
                    "--- a/MODULE.bazel",
                    "+++ b/MODULE.bazel",
                    *lines,
                )
            )

        self.assertFalse(
            changes_registrations(
                diff(
                    "@@ -20 +20 @@ module(",
                    '-bazel_dep(name = "a", version = "1")',
                    '+bazel_dep(name = "a", version = "2")',
                )
            )
        )
        self.assertTrue(
            changes_registrations(
                diff(
                    "@@ -244 +245 @@ godot_engines.build(",
                    '-    enabled_modules = ["a"],',
                    '+    enabled_modules = ["b"],',
                )
            )
        )
        self.assertTrue(
            changes_registrations(
                diff("@@ -266 +266 @@ _REDUCED_RUNTIME = {", '-    "vulkan": "no",')
            )
        )
        self.assertTrue(
            changes_registrations(
                diff(
                    "@@ -300,0 +301,3 @@ use_repo(",
                    "+godot_engine_build(",
                    '+    name = "probe",',
                    "+)",
                )
            )
        )

    def test_a_watched_path_that_no_longer_exists_fails(self) -> None:
        subprocess.run(
            ["git", "rm", "-q", "--cached", ENGINE_PATHS[0] + "BUILD.bazel"],
            cwd=self.root,
            check=True,
        )
        with self.assertRaisesRegex(FileNotFoundError, ENGINE_PATHS[0]):
            watched(self.root)


if __name__ == "__main__":
    unittest.main()
