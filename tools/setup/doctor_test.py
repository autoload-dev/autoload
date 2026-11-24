"""The setup check names what a checkout lacks, as an error or a warning."""

import json
import tempfile
import unittest
from pathlib import Path

from tools.code_health.scan import Unavailable
from tools.setup.doctor import (
    android_findings,
    code_health_findings,
    entire_findings,
    hook_findings,
)

ENTIRE_HOOK = """#!/bin/sh
# Entire CLI hooks
if [ -x '{path}' ]; then '{path}' hooks git post-commit || true; fi
"""


class DoctorTest(unittest.TestCase):
    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.hooks = self.root / "hooks"
        self.hooks.mkdir()

    def enable_entire(self, enabled: bool = True) -> None:
        (self.root / ".entire").mkdir()
        (self.root / ".entire/settings.json").write_text(json.dumps({"enabled": enabled}))

    def test_missing_aspect_hooks_are_errors(self) -> None:
        findings = hook_findings(config=lambda name: "" if "pre-push" in name else "cmd")
        self.assertEqual(len(findings), 1)
        self.assertTrue(findings[0].error)
        self.assertIn("pre-push", findings[0].message)

    def test_missing_hooks_are_warnings_when_bootstrap_skipped_them(self) -> None:
        findings = hook_findings(config=lambda _: "", optional=True)
        self.assertEqual([finding.error for finding in findings], [False, False])

    def test_entire_disabled_locally_is_not_checked(self) -> None:
        self.enable_entire()
        (self.root / ".entire/settings.local.json").write_text(
            json.dumps({"enabled": False})
        )
        self.assertEqual(
            entire_findings(self.root, lambda: self.hooks, which=lambda _: None), []
        )

    def test_invalid_entire_settings_are_a_warning(self) -> None:
        self.enable_entire()
        (self.root / ".entire/settings.json").write_text("<<<<<<< HEAD")
        findings = entire_findings(self.root, lambda: self.hooks, which=lambda _: None)
        self.assertEqual([finding.error for finding in findings], [False])
        self.assertIn("not valid JSON", findings[0].message)

    def test_an_unselected_android_sdk_is_a_warning(self) -> None:
        findings = android_findings({})
        self.assertEqual([finding.error for finding in findings], [False])

    def test_an_incomplete_android_sdk_names_its_missing_packages(self) -> None:
        findings = android_findings({"ANDROID_HOME": str(self.root)})
        self.assertFalse(findings[0].error)
        self.assertIn("ndk;", findings[0].message)

    def test_code_health_needs_no_warning_with_a_token_or_a_session(self) -> None:
        def unavailable() -> None:
            raise Unavailable("CodeScene is not signed in")

        self.assertEqual(
            code_health_findings({"CS_ACCESS_TOKEN": "secret"}, sign_in=unavailable), []
        )
        self.assertEqual(code_health_findings({}, sign_in=lambda: None), [])
        findings = code_health_findings({}, sign_in=unavailable)
        self.assertFalse(findings[0].error)
        self.assertIn("not signed in", findings[0].message)

    def test_entire_is_not_checked_when_the_repository_disables_it(self) -> None:
        self.enable_entire(enabled=False)
        self.assertEqual(
            entire_findings(self.root, lambda: self.hooks, which=lambda _: None), []
        )

    def test_a_missing_entire_is_a_warning(self) -> None:
        self.enable_entire()
        findings = entire_findings(self.root, lambda: self.hooks, which=lambda _: None)
        self.assertEqual([finding.error for finding in findings], [False])
        self.assertIn("not on PATH", findings[0].message)

    def test_missing_entire_git_hooks_are_a_warning(self) -> None:
        self.enable_entire()
        findings = entire_findings(
            self.root, lambda: self.hooks, which=lambda _: "/bin/entire"
        )
        self.assertIn("entire enable", findings[0].message)

    def test_entire_git_hooks_with_a_stale_binary_are_a_warning(self) -> None:
        self.enable_entire()
        stale = self.root / "old/entire"
        for name in ("post-commit", "pre-push"):
            (self.hooks / name).write_text(ENTIRE_HOOK.format(path=stale))
        findings = entire_findings(
            self.root, lambda: self.hooks, which=lambda _: "/bin/entire"
        )
        self.assertEqual(len(findings), 1)
        self.assertIn(str(stale), findings[0].message)
        self.assertIn("entire configure --force", findings[0].message)

    def test_entire_git_hooks_with_an_existing_binary_pass(self) -> None:
        self.enable_entire()
        binary = self.root / "bin/entire"
        binary.parent.mkdir()
        binary.write_text("")
        (self.hooks / "post-commit").write_text(ENTIRE_HOOK.format(path=binary))
        self.assertEqual(
            entire_findings(self.root, lambda: self.hooks, which=lambda _: "/bin/entire"),
            [],
        )


if __name__ == "__main__":
    unittest.main()
