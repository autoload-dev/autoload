"""Tests of the launcher options and install policy every platform shares."""

from __future__ import annotations

import unittest

import launch_desktop
from launch_common import LaunchError, Options, install_resolving_conflicts, parse_options

# A platform that runs on devices and accepts their options.
_DEVICE = frozenset(
    {
        "device",
        "list_devices",
        "fresh",
        "on_conflict",
        "install_only",
        "no_install",
        "env",
    }
)


def _parse(argv: list[str], platform: str = "device") -> Options:
    accepted = launch_desktop.OPTIONS if platform == "desktop" else _DEVICE
    return parse_options(argv, platform, accepted)


class ParseOptionsTest(unittest.TestCase):
    def test_godot_arguments_follow_the_separator(self) -> None:
        options = _parse(["--headless", "--", "--verbose", "--", "--level=3"], "desktop")
        self.assertTrue(options.headless)
        self.assertEqual(options.godot_args, ("--verbose", "--", "--level=3"))

    def test_defaults_install_launch_and_stream(self) -> None:
        options = _parse([])
        self.assertTrue(options.start_device)
        self.assertEqual(options.on_conflict, "uninstall")
        self.assertFalse(options.detach)
        self.assertEqual(options.godot_args, ())

    def test_unknown_arguments_point_at_the_separator(self) -> None:
        with self.assertRaisesRegex(LaunchError, r"bazel run <app> -- -- --verbose"):
            _parse(["--verbose"])

    def test_options_a_platform_does_not_accept_fail(self) -> None:
        with self.assertRaisesRegex(
            LaunchError, "--logcat does not apply to device applications"
        ):
            _parse(["--logcat=all"])
        with self.assertRaisesRegex(
            LaunchError, "--os does not apply to device applications"
        ):
            _parse(["--os=26.4"])

    def test_desktop_has_no_device(self) -> None:
        for flag in (
            "--device=emulator-5554",
            "--list-devices",
            "--on-conflict=fail",
            "--install-only",
        ):
            with self.subTest(flag=flag), self.assertRaisesRegex(LaunchError, "desktop"):
                _parse([flag], "desktop")

    def test_environment_assignments(self) -> None:
        options = _parse(["--env", "A=1", "--env=B=x=y"])
        self.assertEqual(dict(options.env), {"A": "1", "B": "x=y"})
        with self.assertRaisesRegex(LaunchError, "NAME=VALUE"):
            _parse(["--env", "A"])

    def test_install_modes_exclude_each_other(self) -> None:
        with self.assertRaises(SystemExit):
            _parse(["--install-only", "--no-install"])


class InstallPolicyTest(unittest.TestCase):
    def setUp(self) -> None:
        self.failures = ["CONFLICT"]
        self.events: list[str] = []

    def install(self, *argv: str) -> None:
        def attempt() -> str | None:
            self.events.append("install")
            return self.failures.pop(0) if self.failures else None

        install_resolving_conflicts(
            "org.example.game",
            "device",
            _parse(list(argv)),
            install=attempt,
            uninstall=lambda: self.events.append("uninstall"),
            installed=lambda: True,
            conflict=lambda failure: "it conflicts" if failure == "CONFLICT" else None,
        )

    def test_a_conflict_uninstalls_and_retries(self) -> None:
        self.install()
        self.assertEqual(self.events, ["install", "uninstall", "install"])

    def test_on_conflict_fail_keeps_the_installed_copy(self) -> None:
        with self.assertRaisesRegex(LaunchError, "--on-conflict=uninstall"):
            self.install("--on-conflict=fail")
        self.assertEqual(self.events, ["install"])

    def test_other_failures_are_not_retried(self) -> None:
        self.failures = ["BROKEN"]
        with self.assertRaisesRegex(LaunchError, "failed: BROKEN"):
            self.install()
        self.assertEqual(self.events, ["install"])

    def test_fresh_uninstalls_first(self) -> None:
        self.failures = []
        self.install("--fresh")
        self.assertEqual(self.events, ["uninstall", "install"])


if __name__ == "__main__":
    unittest.main()
