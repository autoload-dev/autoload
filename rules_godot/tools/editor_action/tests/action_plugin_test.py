import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tools.editor_action import action as editor_action
from tools.editor_action.action import join_action, run_action

# The record of a successful export.
SUCCESS = {"operation": "export", "verdict": "success", "diagnostics": [], "facts": {}}


class ActionPluginTest(unittest.TestCase):
    def run_stub(
        self, behavior: dict, timeout: int = 300, grace: int = 20
    ) -> tuple[dict | None, str, str]:
        """
        Run an editor action with a stub editor; return its record or None, the
        error and stderr.

        The stub reads behavior from the staged project: the record it writes
        (or none), then whether it hangs and its exit status.
        """
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            editor = base / "editor"
            editor.write_text(
                f"#!{sys.executable}\n"
                "import json, pathlib, sys, time\n"
                "root = pathlib.Path(sys.argv[sys.argv.index('--path') + 1])\n"
                "behavior = json.loads((root / 'stub.json').read_text())\n"
                "action = json.loads((root / 'addons/rules_godot_action/action.json').read_text())\n"
                "if behavior.get('record'):\n"
                "    pathlib.Path(action['record']).write_text(json.dumps(behavior['record']))\n"
                "print('godot output')\n"
                "sys.stdout.flush()\n"
                "if behavior.get('hang'):\n"
                "    time.sleep(60)\n"
                "sys.exit(behavior.get('exit', 0))\n"
            )
            editor.chmod(0o755)
            work, root = base / "work", base / "work" / "project"
            root.mkdir(parents=True)
            (root / "project.godot").write_text("config_version=5\n")
            (root / "stub.json").write_text(json.dumps(behavior))
            join_action(root, work, "export")
            stderr = io.StringIO()
            with (
                mock.patch.object(editor_action, "_ACTION_TIMEOUT_SECONDS", timeout),
                mock.patch.object(editor_action, "_RECORD_GRACE_SECONDS", grace),
                contextlib.redirect_stderr(stderr),
            ):
                try:
                    record = run_action({"editor": str(editor)}, base, root, work, [])
                except RuntimeError as error:
                    return None, str(error), stderr.getvalue()
            return record, "", stderr.getvalue()

    def test_an_action_without_a_record_fails_with_godots_output(self) -> None:
        record, error, _ = self.run_stub({"exit": 0})
        self.assertIsNone(record)
        self.assertIn("ended without recording its export result", error)
        self.assertIn("godot output", error)

    def test_a_failure_record_fails_with_its_diagnostics(self) -> None:
        failure = {
            "operation": "export",
            "verdict": "failure",
            "diagnostics": ["Save PCK: Can't open file for writing"],
            "facts": {},
        }
        record, error, _ = self.run_stub({"record": failure, "exit": 1})
        self.assertIsNone(record)
        self.assertIn("Save PCK: Can't open file for writing", error)
        self.assertIn("godot output", error)

    def test_a_crash_after_a_success_record_is_a_note(self) -> None:
        success = SUCCESS
        record, error, stderr = self.run_stub({"record": success, "exit": 134})
        self.assertEqual(
            ("", success | {"output": "godot output\n", "stopped": False}),
            (error, record),
        )
        self.assertIn("ended with exit status 134 after a successful export", stderr)

    def test_godot_is_stopped_a_grace_period_after_its_record(self) -> None:
        success = SUCCESS
        record, error, stderr = self.run_stub({"record": success, "hang": True}, grace=1)
        self.assertEqual(
            ("", success | {"output": "godot output\n", "stopped": True}), (error, record)
        )
        self.assertIn("stopped Godot 1 seconds after its export result", stderr)

    def test_an_action_without_a_record_in_time_fails(self) -> None:
        record, error, _ = self.run_stub({"hang": True}, timeout=1)
        self.assertIsNone(record)
        self.assertIn("recorded no export result within 1 seconds", error)

    def test_the_action_plugin_joins_hidden_from_scans_and_exports(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            work = Path(temp)
            root = work / "project"
            root.mkdir()
            authored = '[editor_plugins]\n\nenabled=PackedStringArray("res://addons/a/plugin.cfg")\n'
            (root / "project.godot").write_text(authored)
            join_action(root, work, "features", {"tags": ["mobile"]})
            directory = root / "addons/rules_godot_action"
            self.assertTrue((directory / ".gdignore").exists())
            self.assertEqual(authored, (work / "project.godot").read_text())
            self.assertIn(
                '"res://addons/a/plugin.cfg", "res://addons/rules_godot_action/plugin.cfg"',
                (root / "project.godot").read_text(),
            )
            action = json.loads((directory / "action.json").read_text())
            self.assertEqual(
                {
                    "operation": "features",
                    "tags": ["mobile"],
                    "record": str(work / "record.json"),
                    "project_file": str(work / "project.godot"),
                },
                action,
            )
            with self.assertRaisesRegex(ValueError, "reserved for rules_godot"):
                join_action(root, work, "features")

    def test_a_further_plugin_joins_the_same_way_at_its_reserved_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            work = Path(temp) / "work"
            root = work / "project"
            root.mkdir(parents=True)
            (root / "project.godot").write_text("config_version=5\n")
            source = Path(temp) / "plugin"
            source.mkdir()
            (source / "plugin.cfg").write_text("[plugin]\n")
            plugins = {"addons/rules_godot_extra": source}
            join_action(root, work, "profile", None, plugins)
            directory = root / "addons/rules_godot_extra"
            self.assertTrue((directory / "plugin.cfg").exists())
            self.assertTrue((directory / ".gdignore").exists())
            project = (root / "project.godot").read_text()
            self.assertIn("res://addons/rules_godot_extra/plugin.cfg", project)
            self.assertIn("res://addons/rules_godot_action/plugin.cfg", project)
            self.assertNotIn("rules_godot_extra", (work / "project.godot").read_text())
            taken = Path(temp) / "taken"
            (taken / "project/addons/rules_godot_extra").mkdir(parents=True)
            (taken / "project/project.godot").write_text("config_version=5\n")
            with self.assertRaisesRegex(ValueError, "rules_godot_extra is reserved"):
                join_action(taken / "project", taken, "profile", None, plugins)


if __name__ == "__main__":
    unittest.main()
