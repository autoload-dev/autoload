"""Contract tests for the runtime profile: composition, rendering, derivation and sync."""

import contextlib
import io
import json
import tempfile
import unittest
from collections.abc import Callable
from pathlib import Path
from typing import Any
from unittest import mock

from tools import runtime_profile
from tools.runtime_profile import (
    ProfileError,
    check_file,
    compose_profile,
    derive,
    place_file,
    render_profile,
)

_DETECTED: dict[str, Any] = {
    "type": "build_profile",
    "disabled_classes": ["Camera3D", "Image", "Script", "Skeleton3D"],
    "disabled_build_options": {
        "disable_3d": True,
        "disable_xr": True,
        "forward_plus_renderer": False,
        "module_openxr_enabled": False,
        "vulkan": False,
    },
}


class CompositionTest(unittest.TestCase):
    def test_the_keep_list_is_subtracted_from_the_detected_classes(self) -> None:
        profile = compose_profile(_DETECTED, keep=["Image", "Script"])
        self.assertEqual(["Camera3D", "Skeleton3D"], profile["disabled_classes"])

    def test_a_kept_class_the_detection_did_not_name_changes_nothing(self) -> None:
        profile = compose_profile(_DETECTED, keep=["Gradient"])
        self.assertEqual(
            ["Camera3D", "Image", "Script", "Skeleton3D"], profile["disabled_classes"]
        )

    def test_the_profile_keeps_every_detected_option_and_module_switch(self) -> None:
        profile = compose_profile(_DETECTED, keep=["Image"])
        self.assertEqual(
            _DETECTED["disabled_build_options"], profile["disabled_build_options"]
        )
        self.assertIn("module_openxr_enabled", profile["disabled_build_options"])

    def test_the_profile_keeps_godots_type_and_sorts_its_classes(self) -> None:
        profile = compose_profile(
            {"disabled_classes": ["B", "A"], "disabled_build_options": {}}, keep=[]
        )
        self.assertEqual("build_profile", profile["type"])
        self.assertEqual(["A", "B"], profile["disabled_classes"])

    def test_a_detection_without_the_expected_fields_is_rejected(self) -> None:
        with self.assertRaises(ProfileError):
            compose_profile({"type": "build_profile"}, keep=[])


class RenderingTest(unittest.TestCase):
    def test_the_profile_is_godots_sorted_tab_indented_json(self) -> None:
        text = render_profile(
            {
                "type": "build_profile",
                "disabled_classes": ["A"],
                "disabled_build_options": {},
            }
        )
        self.assertEqual(
            '{\n\t"disabled_build_options": {},\n\t"disabled_classes": [\n\t\t"A"\n\t],\n'
            '\t"type": "build_profile"\n}\n',
            text,
        )
        self.assertEqual("A", json.loads(text)["disabled_classes"][0])


class DeriveTest(unittest.TestCase):
    def run_derive(self, detected: dict | None, **manifest: object) -> Path:
        """Derive with a stub editor that records detected as the plugin's saved profile."""
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        base = Path(temp.name)
        (base / "project.godot").write_text("config_version=5\n")
        self.profile = base / "out" / "app.gdbuild"
        self.profile.parent.mkdir()
        self.argv: list[str] = []

        def editor(
            manifest: dict, execroot: Path, root: Path, work: Path, args: list[str]
        ) -> dict:
            self.argv = args
            plugin = json.loads(
                (root / "addons/rules_godot_action/action.json").read_text()
            )
            self.assertTrue((root / "addons/rules_godot_profile/plugin.gd").is_file())
            self.assertIn("rules_godot_profile", (root / "project.godot").read_text())
            if detected is not None:
                Path(plugin["profile"]).write_text(json.dumps(detected))
            return {"facts": {}, "output": ""}

        data = {
            "project_file": "project.godot",
            "member_resource_paths": {},
            "keep_classes": ["Image"],
            "editor": "editor",
        } | manifest
        with mock.patch.object(runtime_profile, "run_action", editor):
            derive(data, self.profile, base)
        return self.profile

    def test_it_runs_the_editor_with_the_profile_plugin_and_writes_the_profile(
        self,
    ) -> None:
        profile = self.run_derive(_DETECTED)
        self.assertEqual(["--editor"], self.argv)
        written = json.loads(profile.read_text())
        self.assertEqual(
            ["Camera3D", "Script", "Skeleton3D"], written["disabled_classes"]
        )
        self.assertEqual(
            _DETECTED["disabled_build_options"], written["disabled_build_options"]
        )

    def test_a_missing_profile_from_the_plugin_fails_the_action(self) -> None:
        with self.assertRaisesRegex(ProfileError, "wrote no profile"):
            self.run_derive(None)


class SyncTest(unittest.TestCase):
    def setUp(self) -> None:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.base = Path(temp.name)
        self.workspace = self.base / "workspace"
        (self.workspace / "app").mkdir(parents=True)
        self.built = self.base / "built.gdbuild"
        self.built.write_text("derived\n")
        self.checked_in = self.base / "checked.gdbuild"

    def capture(
        self, function: Callable[..., Any], *args: Any, **kwargs: Any
    ) -> tuple[Any, str]:
        """Call function and return its result and the report on stderr."""
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            result = function(*args, **kwargs)
        return result, stderr.getvalue()

    def place(self) -> str:
        return self.capture(place_file, self.built, "app/app.gdbuild", self.workspace)[1]

    def check(self, checked_in: Path) -> tuple[int, str]:
        return self.capture(
            check_file, self.built, checked_in, "app/app.gdbuild", "//app:profile"
        )

    def test_writing_creates_the_file_and_names_it_for_commit(self) -> None:
        report = self.place()
        self.assertEqual("derived\n", (self.workspace / "app/app.gdbuild").read_text())
        self.assertIn("wrote app/app.gdbuild; commit it", report)

    def test_writing_leaves_an_up_to_date_file_alone(self) -> None:
        target = self.workspace / "app/app.gdbuild"
        target.write_text("derived\n")
        before = target.stat().st_mtime_ns
        report = self.place()
        self.assertEqual(before, target.stat().st_mtime_ns)
        self.assertNotIn("wrote", report)

    def test_a_stale_file_is_replaced(self) -> None:
        target = self.workspace / "app/app.gdbuild"
        target.write_text("old\n")
        self.place()
        self.assertEqual("derived\n", target.read_text())

    def test_the_test_fails_for_an_empty_file_and_names_the_command(self) -> None:
        # The file a user creates empty before the first run.
        self.checked_in.write_text("")
        status, report = self.check(self.checked_in)
        self.assertEqual(1, status)
        self.assertIn("app/app.gdbuild does not match", report)
        self.assertIn("bazel run //app:profile", report)

    def test_the_test_fails_for_a_stale_file_and_shows_the_difference(self) -> None:
        self.checked_in.write_text("old\n")
        status, report = self.check(self.checked_in)
        self.assertEqual(1, status)
        self.assertIn("app/app.gdbuild does not match", report)
        self.assertIn("-old", report)
        self.assertIn("+derived", report)

    def test_the_test_passes_for_an_up_to_date_file(self) -> None:
        self.checked_in.write_text("derived\n")
        status, _ = self.check(self.checked_in)
        self.assertEqual(0, status)


if __name__ == "__main__":
    unittest.main()
