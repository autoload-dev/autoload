"""The Bazel wrapper (tools/bazel): slots and profiles choose each workspace's output base."""

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

WRAPPER = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path("tools/bazel")


class BazelWrapperTest(unittest.TestCase):
    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        (self.root / ".git").mkdir()
        (self.root / "MODULE.bazel").write_text("")
        (self.root / "tools").mkdir()
        shutil.copyfile(WRAPPER, self.root / "tools/bazel")
        (self.root / "tools/bazel").chmod(0o755)
        # Bazel itself: prints the arguments it receives, one per line.
        self.bazel = self.root / "bazel_real"
        self.bazel.write_text('#!/usr/bin/env bash\nprintf "%s\\n" "$@"\n')
        self.bazel.chmod(0o755)

    def run_wrapper(
        self, *arguments: str, module: Path | None = None, **env: str
    ) -> list[str]:
        variables = {
            key: value
            for key, value in os.environ.items()
            if not key.startswith(("AUTOLOAD_BAZEL", "RULES_GODOT_BAZEL"))
        }
        variables.update(BAZEL_REAL=str(self.bazel), HOME=str(self.root), **env)
        result = subprocess.run(
            [str((module or self.root) / "tools/bazel"), *arguments],
            cwd=module or self.root,
            env=variables,
            check=True,
            capture_output=True,
            text=True,
        )
        return result.stdout.split()

    def test_the_default_profile_keeps_bazel_s_own_output_base(self) -> None:
        self.assertEqual(["build", "//..."], self.run_wrapper("build", "//..."))

    def test_a_profile_has_an_output_base_and_an_idle_limit_of_its_own(self) -> None:
        android = self.run_wrapper("build", "//...", AUTOLOAD_BAZEL_PROFILE="android")
        ios = self.run_wrapper("build", "//...", AUTOLOAD_BAZEL_PROFILE="ios")
        self.assertEqual(android[-2:], ["build", "//..."])
        self.assertIn("--max_idle_secs=900", android)
        bases = [
            next(a for a in arguments if a.startswith("--output_base="))
            for arguments in (android, ios)
        ]
        self.assertNotEqual(bases[0], bases[1])
        for base in bases:
            self.assertRegex(base, r"/_bazel_[^/]+/[0-9a-f]{32}$")
        self.assertEqual(
            bases[0],
            next(
                a
                for a in self.run_wrapper("info", AUTOLOAD_BAZEL_PROFILE="android")
                if a.startswith("--output_base=")
            ),
        )

    def test_a_profile_of_a_slot_lies_beside_the_slot_s_base(self) -> None:
        slot = self.root / "slots" / ("a" * 32)
        (self.root / ".bazel-slot").write_text(f". {slot}\n")
        self.assertEqual([f"--output_base={slot}", "build"], self.run_wrapper("build"))
        profiled = self.run_wrapper("build", AUTOLOAD_BAZEL_PROFILE="ios")
        base = next(a for a in profiled if a.startswith("--output_base="))
        self.assertEqual(Path(base.removeprefix("--output_base=")).parent, slot.parent)
        self.assertNotEqual(base, f"--output_base={slot}")

    def test_a_profile_lies_in_the_output_user_root_an_rc_file_names(self) -> None:
        # A CI runner's ~/.bazelrc points Bazel at its slot's output user root; a profile's
        # base belongs there too, not in Bazel's default root under the runner's home.
        (self.root / ".bazelrc").write_text(
            "build --config=ci\nstartup --output_user_root=/slots/1/bazel\n"
        )
        profiled = self.run_wrapper("build", AUTOLOAD_BAZEL_PROFILE="android")
        base = next(a for a in profiled if a.startswith("--output_base="))
        self.assertRegex(base, r"^--output_base=/slots/1/bazel/[0-9a-f]{32}$")

    def test_a_nested_module_keeps_its_own_output_base_under_a_profile(self) -> None:
        # The ruleset's commands that root-module work starts, such as the contract
        # checker's, keep the ruleset's default server.
        ruleset = self.root / "rules_godot"
        (ruleset / "tools").mkdir(parents=True)
        (ruleset / "MODULE.bazel").write_text("")
        (ruleset / "tools/bazel").symlink_to("../../tools/bazel")
        self.assertEqual(
            ["build"],
            self.run_wrapper("build", module=ruleset, AUTOLOAD_BAZEL_PROFILE="android"),
        )

    def test_an_explicit_output_base_wins(self) -> None:
        self.assertEqual(
            ["--output_base=/x", "build"],
            self.run_wrapper("--output_base=/x", "build", AUTOLOAD_BAZEL_PROFILE="ios"),
        )


if __name__ == "__main__":
    unittest.main(argv=sys.argv[:1])
