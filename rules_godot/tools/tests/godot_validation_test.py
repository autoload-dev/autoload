"""How a unit's validation decides from what Godot reports while each file loads."""

import tempfile
import unittest
from pathlib import Path

from tools.godot_validation import (
    closure_autoloads,
    extensions_hint,
    remove_tool_mode,
    typed_autoloads,
    verdict,
    without_tool_mode,
)

_SCRIPT = "res://unit/broken.gd"
_SCENE = "res://unit/level.tscn"


class GodotValidationTest(unittest.TestCase):
    def test_errors_fail_with_file_and_line(self) -> None:
        result = verdict(
            {
                _SCRIPT: [
                    {
                        "type": "script",
                        "file": _SCRIPT,
                        "line": 4,
                        "text": 'Parse Error: Expected closing ")" after call arguments.',
                    },
                    {
                        "type": "error",
                        "file": "modules/gdscript/gdscript.cpp",
                        "line": 2907,
                        "text": 'Failed to load script "res://unit/broken.gd" with error "Parse error".',
                    },
                ]
            },
            "sync",
        )
        self.assertEqual(
            [
                'res://unit/broken.gd:4: Parse Error: Expected closing ")" after call arguments.',
                (
                    'res://unit/broken.gd: Failed to load script "res://unit/broken.gd" '
                    'with error "Parse error". (modules/gdscript/gdscript.cpp:2907)'
                ),
            ],
            result["failures"],
        )
        self.assertEqual([], result["warnings"])

    def test_a_stale_uid_fails_only_where_uids_are_required(self) -> None:
        # Godot loads a reference whose uid it does not know by its path, with a warning.
        findings = {
            _SCENE: [
                {
                    "type": "warning",
                    "file": "scene/resources/resource_format_text.cpp",
                    "line": 501,
                    "text": "res://unit/level.tscn:5 - ext_resource, invalid UID: "
                    "uid://b1 - using text path instead: res://unit/icon.png",
                }
            ]
        }
        for mode, failing in [("off", False), ("sync", False), ("require", True)]:
            with self.subTest(mode=mode):
                result = verdict(findings, mode)
                self.assertEqual(failing, bool(result["failures"]))
                self.assertEqual(not failing, bool(result["warnings"]))

    def test_other_warnings_never_fail(self) -> None:
        result = verdict(
            {_SCENE: [{"type": "warning", "file": "x.cpp", "line": 1, "text": "Note"}]},
            "require",
        )
        self.assertEqual(
            {"failures": [], "warnings": [f"{_SCENE}: Note (x.cpp:1)"]}, result
        )


def _scene(root: str, *resources: str) -> str:
    """A text scene with ext_resources (id, path) and a root node's heading and body."""
    return (
        "[gd_scene format=3]\n\n"
        + "".join(
            f'[ext_resource type="Script" path="{path}" id="{id}"]\n'
            for id, path in (resource.split("=", 1) for resource in resources)
        )
        + f"\n{root}\n\n"
        + '[node name="Child" type="Node" parent="."]\nscript = ExtResource("child")\n'
    )


# The UIDs of a staged closure and its resource paths; res://outside.gd is no member.
_UIDS = {"res://ui/hud.tscn": "uid://b3x7hud", "res://outside.gd": "uid://c9out"}
_MEMBERS = frozenset({"state.gd", "ui/hud.tscn", "tracker.gd", "declared.gd"})


class ExtensionsHintTest(unittest.TestCase):
    def test_no_hint_when_every_extension_loaded(self) -> None:
        self.assertEqual(extensions_hint({}), "")

    def test_both_kinds_get_a_line_each(self) -> None:
        hint = extensions_hint(
            {
                "absent_extensions": ["native/a.gdextension"],
                "toolless_extensions": ["native/b.gdextension"],
            }
        )
        lines = hint.splitlines()
        self.assertEqual(len(lines), 2)
        self.assertIn("res://native/a.gdextension", lines[0])
        self.assertIn("res://native/b.gdextension", lines[1])


class ClosureAutoloadsTest(unittest.TestCase):
    def test_authored_autoloads_whose_files_the_closure_holds(self) -> None:
        self.assertEqual(
            {"State": "*res://state.gd", "Tracker": "res://tracker.gd"},
            closure_autoloads(
                {
                    "State": "*res://state.gd",
                    "Tracker": "res://tracker.gd",
                    "Missing": "*res://missing.gd",
                },
                {},
                _UIDS,
                _MEMBERS,
            ),
        )

    def test_uids_resolve_to_the_closure_files_declaring_them(self) -> None:
        self.assertEqual(
            {"Hud": "*res://ui/hud.tscn"},
            closure_autoloads(
                {
                    "Hud": "*uid://b3x7hud",
                    "Outside": "*uid://c9out",
                    "Unknown": "uid://d0none",
                },
                {},
                _UIDS,
                _MEMBERS,
            ),
        )

    def test_declared_autoloads_replace_authored_ones_of_their_name(self) -> None:
        self.assertEqual(
            {
                "State": "*res://declared.gd",
                "Tracker": "res://tracker.gd",
                "Hud": "*res://ui/hud.tscn",
            },
            closure_autoloads(
                {"State": "*res://state.gd", "Tracker": "res://tracker.gd"},
                {
                    "State": "*res://declared.gd",
                    # Left out, so the authored one of its name stays.
                    "Tracker": "*res://missing.gd",
                    "Hud": "*res://ui/hud.tscn",
                },
                _UIDS,
                _MEMBERS,
            ),
        )


class TypedAutoloadsTest(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        scenes = {
            "ui/hud.tscn": _scene(
                '[node name="Hud" type="Control"]\nscript = ExtResource("1_h")',
                "1_h=hud.gd",
                "child=res://ui/child.gd",
            ),
            "ui/plain.tscn": _scene(
                '[node name="Plain" type="Node"]', "child=res://ui/child.gd"
            ),
            "ui/builtin.tscn": _scene(
                '[node name="Builtin" type="Node"]\nscript = SubResource("GDScript_x")',
                "child=res://ui/child.gd",
            ),
            "ui/inherited.tscn": _scene(
                '[node name="Hud" instance=ExtResource("base")]',
                "base=res://ui/hud.tscn",
                "child=res://ui/child.gd",
            ),
        }
        for path, text in scenes.items():
            (self.root / path).parent.mkdir(parents=True, exist_ok=True)
            (self.root / path).write_text(text, encoding="utf-8")

    def test_scripts_keep_their_values(self) -> None:
        autoloads = {"Tracker": "*res://tracker.gd", "Plain": "res://plain.gd"}
        self.assertEqual(autoloads, typed_autoloads(self.root, autoloads))

    def test_scenes_are_typed_by_their_root_script(self) -> None:
        self.assertEqual(
            {
                "Hud": "*res://ui/hud.gd",
                "Inherited": "*res://ui/hud.gd",
                "Unmarked": "res://ui/hud.gd",
            },
            typed_autoloads(
                self.root,
                {
                    "Hud": "*res://ui/hud.tscn",
                    "Inherited": "*res://ui/inherited.tscn",
                    "Unmarked": "res://ui/hud.tscn",
                },
            ),
        )

    def test_scenes_without_a_root_script_file_stay_nodes(self) -> None:
        self.assertEqual(
            {},
            typed_autoloads(
                self.root,
                {
                    "Plain": "*res://ui/plain.tscn",
                    "Builtin": "*res://ui/builtin.tscn",
                    "Binary": "*res://ui/level.scn",
                    "Missing": "*res://ui/missing.tscn",
                },
            ),
        )


class WithoutToolModeTest(unittest.TestCase):
    def test_annotations_starting_a_line_leave_with_the_blanks_after_them(self) -> None:
        source = (
            "@tool @abstract\n"
            "extends Node\n"
            '@export_tool_button("Bake", "Bake") var bake: Callable = func(): pass\n'
            "class Inner:\n"
            "\t@export_tool_button(\n"
            '\t\t"Clear (all)"\n'
            "\t) var clear := clear_all\n"
            "@export var size := 1\n"
        )
        self.assertEqual(
            (
                "@abstract\n"
                "extends Node\n"
                "var bake: Callable = func(): pass\n"
                "class Inner:\n"
                "\t\n"
                "\n"
                "\tvar clear := clear_all\n"
                "@export var size := 1\n"
            ),
            without_tool_mode("res://a.gd", source),
        )

    def test_annotations_after_code_become_spaces(self) -> None:
        source = '@icon("res://a.svg") @tool\nextends Node\n'
        self.assertEqual(
            '@icon("res://a.svg")      \nextends Node\n',
            without_tool_mode("res://a.gd", source),
        )

    def test_strings_comments_and_other_annotations_stay(self) -> None:
        source = (
            "extends Node # @tool\n"
            'const HINT = "@tool"\n'
            'const DOC = """\n@tool\n"""\n'
            "@tooling var x\n"
            '@icon("res://tool.svg") var y\n'
        )
        self.assertEqual(source, without_tool_mode("res://a.gd", source))

    def test_carriage_returns_stay(self) -> None:
        self.assertEqual(
            "\r\nextends Node\r\n",
            without_tool_mode("res://a.gd", "@tool\r\nextends Node\r\n"),
        )

    def test_built_in_scripts_of_text_scenes_lose_their_annotations(self) -> None:
        scene = (
            "[gd_scene format=3]\n\n"
            '[sub_resource type="GDScript" id="GDScript_a"]\n'
            'script/source = "@tool\n'
            "extends Node\n"
            '@export_tool_button(\\"Go \\\\ \\u00e9\\") var go = func(): pass\n'
            '"\n\n'
            '[sub_resource type="Resource" id="Resource_b"]\n'
            'script/source = "@tool"\n\n'
            '[node name="Root" type="Node"]\n'
            'script = SubResource("GDScript_a")\n'
            'editor_description = "@tool"\n'
        )
        expected = scene.replace('"@tool\nextends', '"\nextends', 1).replace(
            '@export_tool_button(\\"Go \\\\ \\u00e9\\") ', ""
        )
        self.assertEqual(expected, without_tool_mode("res://level.tscn", scene))

    def test_files_that_are_no_utf8_text_are_reported(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        latin1 = '[gd_scene format=3]\n[sub_resource type="GDScript" id="a"]\n'
        latin1 += 'script/source = "@tool\nextends Node # caf\u00e9\n"\n'
        files = {
            "tool.gd": b"@tool\nextends Node\n",
            "level.tscn": latin1.encode("latin-1"),
            "icon.png": b"\x89PNG\xff",
            ".godot/cache.tres": b"\xff",
        }
        for path, data in files.items():
            (root / path).parent.mkdir(parents=True, exist_ok=True)
            (root / path).write_bytes(data)
        self.assertEqual(["res://level.tscn"], remove_tool_mode(root, files))
        self.assertEqual(b"\nextends Node\n", (root / "tool.gd").read_bytes())
        self.assertEqual(files["level.tscn"], (root / "level.tscn").read_bytes())


if __name__ == "__main__":
    unittest.main()
