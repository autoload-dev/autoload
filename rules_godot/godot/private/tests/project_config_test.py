"""Configuration preservation, strict literal handling and the project.godot of each purpose."""

import functools
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from godot.private import project_config
from godot.private.project_config import (
    authored_autoloads,
    enable_plugins,
    left_out,
    named_paths,
    override_applies,
    override_tags,
    setting_kind,
    shadowed,
    statement_groups,
    validate_literal,
    write_back,
)


def _runfile(name: str) -> str:
    return (
        Path(os.environ["TEST_SRCDIR"])
        / os.environ["TEST_WORKSPACE"]
        / "godot/private/tests"
        / name
    ).read_text(encoding="utf-8")


# The setting kinds and sections of Godot 4.7, from godot/private/engine/setting_kinds.bzl.
_TABLE = json.loads(_runfile("setting_kinds.json"))
KINDS = _TABLE["kinds"]
SECTIONS = _TABLE["sections"]


# Construct with Godot 4.7's setting kinds, as the rules do.
compose_project = functools.partial(
    project_config.compose_project, kinds=KINDS, sections=SECTIONS
)


def _run(
    command: str, work: Path, data: dict, output: str = "left_out.json"
) -> subprocess.CompletedProcess:
    """Run a project_config command on data, writing output in work."""
    manifest = work / f"{command}.config.json"
    manifest.write_text(json.dumps(data))
    return subprocess.run(
        [
            sys.executable,
            project_config.__file__,
            command,
            "--manifest",
            str(manifest),
            "--output",
            str(work / output),
        ],
        capture_output=True,
        text=True,
        check=False,
    )


class ProjectConfigTest(unittest.TestCase):
    def test_preserves_multiline_authored_values(self) -> None:
        base = '; authored\nconfig_version=5\n[application]\nconfig/name="Base"\n[custom]\nvalue={\n"nested": [1, 2],\n}\n'
        text = compose_project(
            base,
            {"application/config/name": '"Demo"'},
            {"State": "*res://state.gd"},
            "res://demo.tscn",
        )
        self.assertIn("; authored", text)
        self.assertIn('value={\n"nested": [1, 2],\n}', text)
        self.assertNotIn('config/name="Base"', text)
        self.assertIn('config/name="Demo"', text)
        self.assertIn('State="*res://state.gd"', text)
        self.assertIn('run/main_scene="res://demo.tscn"', text)

    def test_runtime_only_changes_do_not_change_the_import_configuration(self) -> None:
        base = 'config_version=5\n[application]\nconfig/name="Stable UID seed"\nrun/main_scene="res://%s.tscn"\n[autoload]\nApp="*res://%s.gd"\n[editor_plugins]\nenabled=PackedStringArray("res://%s/plugin.cfg")\n[rendering]\ntextures/default_filters/use_nearest_mipmap_filter=false\n'
        first = compose_project(
            base % ("first", "first", "first"), {}, {}, "", purpose="import"
        )
        second = compose_project(
            base % ("second", "second", "second"), {}, {}, "", purpose="import"
        )
        self.assertEqual(first, second)
        self.assertIn('config/name="Stable UID seed"', first)
        self.assertNotIn("[autoload]", first)
        self.assertNotIn("[editor_plugins]", first)
        changed = compose_project(
            (base % ("first", "first", "first")).replace("false", "true"),
            {},
            {},
            "",
            purpose="import",
        )
        self.assertNotEqual(first, changed)

    def test_import_purpose_omits_settings_that_name_resources(self) -> None:
        base = (
            'config_version=5\n[application]\nconfig/name="Demo"\n'
            'config/description="not res://a path"\n'
            'boot_splash/image="res://splash.png"\nconfig/icon="uid://b4x1"\n'
            '[gui]\ntheme/custom="res://theme.tres"\n'
            "[internationalization]\nlocale/translations=PackedStringArray(\n"
            '"res://en.translation",\n"res://de.translation"\n)\n'
        )
        settings = {"gui/theme/custom_font": '"res://font.ttf"', "rendering/flag": "true"}
        configured = compose_project(base, settings, {}, "", purpose="import")
        for absent in (
            "splash.png",
            "uid://b4x1",
            "theme.tres",
            "translation",
            "font.ttf",
        ):
            self.assertNotIn(absent, configured)
        for present in (
            'config/name="Demo"',
            'description="not res://a path"',
            "flag=true",
        ):
            self.assertIn(present, configured)
        renamed = base.replace("theme.tres", "other.tres")
        self.assertEqual(
            configured, compose_project(renamed, settings, {}, "", purpose="import")
        )

    def test_import_purpose_omits_the_main_scene_even_when_empty(self) -> None:
        base = 'config_version=5\n[application]\nconfig/name="Demo"\nrun/main_scene=%s\n'
        self.assertEqual(
            compose_project(base % '"res://main.tscn"', {}, {}, "", purpose="import"),
            compose_project(base % '""', {}, {}, "", purpose="import"),
        )

    def test_kinds_decide_which_purposes_carry_a_setting(self) -> None:
        # FR-003, D13: the table and Godot's sections decide, not the value: a key
        # outside Godot's sections reaches no import, whatever it names, and the
        # editor's script templates reach only the editor view.
        base = (
            'config_version=5\n[addon_own]\npath="res://data.tres"\nflag=true\n'
            '[editor]\nscript/templates_search_path="res://templates"\n'
            '[rendering]\nnote="res://not_a_setting_kind"\n'
        )
        imported = compose_project(
            base, {"addon_own/level": "3"}, {}, "", purpose="import"
        )
        self.assertNotIn("addon_own", imported)
        self.assertNotIn("templates", imported)
        self.assertIn('note="res://not_a_setting_kind"', imported)
        for purpose in ("runtime", "export"):
            with self.subTest(purpose=purpose):
                text = compose_project(
                    base, {"addon_own/level": "3"}, {}, "", purpose=purpose
                )
                self.assertIn('path="res://data.tres"', text)
                self.assertIn("level=3", text)
                self.assertNotIn("templates", text)
        edited = compose_project(base, {}, {}, "", purpose="editor")
        self.assertIn('script/templates_search_path="res://templates"', edited)

    def test_authored_content_bound_settings_leave_with_their_file(self) -> None:
        # FR-005, FR-029: an authored setting whose file the view lacks is left out
        # of every purpose; a uid:// value and a context-bound setting stay.
        base = (
            'config_version=5\n[application]\nconfig/icon="res://icon.svg"\n'
            'run/main_scene="uid://b4x1"\n[gui]\ntheme/custom="res://theme.tres"\n'
            "[internationalization]\nlocale/translation_remaps={\n"
            '"res://hello.ogg": PackedStringArray("res://hello_de.ogg:de")\n}\n'
            '[shader_globals]\nnoise={\n"type": "sampler2D",\n"value": "res://noise.png"\n}\n'
        )
        members = ["hello.ogg", "noise.png"]
        entries = left_out(base, KINDS, members)
        self.assertEqual(
            [
                ("gui/theme/custom", "res://theme.tres"),
                ("internationalization/locale/translation_remaps", "res://hello_de.ogg"),
            ],
            entries,
        )
        text = compose_project(
            base, {}, {}, "", excluded=[setting for setting, _ in entries]
        )
        for absent in ("theme.tres", "translation_remaps"):
            self.assertNotIn(absent, text)
        for present in ("res://icon.svg", "uid://b4x1", "res://noise.png"):
            self.assertIn(present, text)
        self.assertEqual(
            [], left_out(base, KINDS, members + ["theme.tres", "hello_de.ogg"])
        )

    def test_a_directory_a_setting_names_stays_with_a_file_below_it(self) -> None:
        # FR-032: a setting Godot does not hint as a file may name a directory, which a
        # member below it provides; a file-hinted setting and an autoload name files.
        base = (
            "config_version=5\n[internationalization]\n"
            'locale/translations=PackedStringArray("res://locale")\n'
            '[gui]\ntheme/custom="res://locale"\n[autoload]\nLocale="*res://locale"\n'
        )
        self.assertEqual(
            [("gui/theme/custom", "res://locale"), ("autoload/Locale", "res://locale")],
            left_out(base, KINDS, ["locale/de.po"]),
        )
        self.assertEqual(
            [
                ("internationalization/locale/translations", "res://locale"),
                ("gui/theme/custom", "res://locale"),
                ("autoload/Locale", "res://locale"),
            ],
            left_out(base, KINDS, ["locale.po"]),
        )

    def test_an_override_no_feature_of_the_entry_has_needs_no_file(self) -> None:
        # A view leaves out every override whose file it lacks; a program entry fails only
        # for those that can apply to it, so one whose tag the entry never has, such as a
        # test runner's custom feature, needs no file.
        work = Path(tempfile.mkdtemp())
        base = work / "project.godot"
        base.write_text(
            "config_version=5\n[application]\n"
            'run/main_scene.gdunit_host="res://tests/host.tscn"\n'
            'run/main_scene.mobile="res://mobile.tscn"\n'
        )
        self.assertEqual(2, len(left_out(base.read_text(), KINDS, [])))
        failed = _run(
            "left-out",
            work,
            {
                "project_file": str(base),
                "kinds": KINDS,
                "members": [],
                "program_entry": "//game:pack",
                "features": ["android", "mobile"],
            },
        )
        self.assertNotEqual(0, failed.returncode)
        self.assertIn("Setting application/run/main_scene.mobile", failed.stderr)
        self.assertNotIn("gdunit_host", failed.stderr)

    def test_setting_values_decide_as_in_analysis(self) -> None:
        # view.bzl decides the same cases during analysis (setting_values.bzl).
        for case in json.loads(_runfile("setting_value_cases.json")):
            with self.subTest(key=case["key"], literal=case["literal"]):
                kind = setting_kind(case["key"], KINDS, SECTIONS)
                decided = (
                    [kind["binding"], named_paths(kind["shape"], case["literal"])]
                    if kind
                    else None
                )
                self.assertEqual(case["expected"], decided)
                self.assertEqual(case["expected"], case["starlark"])

    def test_authored_overrides_of_flag_settings_conflict(self) -> None:
        # A feature override would hide the flag's value; the base value and the flag's
        # own key are replaced, and other settings of the section stay unrelated.
        base = (
            "[application]\nconfig/build_number=1\nconfig/build_number.mobile=2\n"
            'config/server.debug_tools="a"\nconfig/server.web="b"\nconfig/name="x"\n'
        )
        found = shadowed(
            base,
            {
                "application/config/build_number": "//:build",
                "application/config/server.debug_tools": "//:server",
            },
        )
        self.assertEqual(2, len(found))
        with tempfile.TemporaryDirectory() as temporary:
            work = Path(temporary)
            (work / "project.godot").write_text(base)
            failed = _run(
                "shadowed",
                work,
                {
                    "project_file": str(work / "project.godot"),
                    "flag_keys": {"application/config/build_number": "//:build"},
                },
                "shadowed.checked",
            )
            self.assertNotEqual(0, failed.returncode)
            self.assertIn(
                "overrides application/config/build_number.mobile", failed.stderr
            )
        self.assertIn("application/config/build_number.mobile", found[0])
        self.assertIn("//:build", found[0])
        self.assertIn("application/config/server.web", found[1])
        self.assertEqual([], shadowed(base, {"application/config/name": "//:name"}))

    def test_overrides_apply_as_in_analysis(self) -> None:
        # view.bzl decides the same cases for a program entry's view (setting_values.bzl).
        for case in json.loads(_runfile("override_cases.json")):
            with self.subTest(key=case["key"], features=case["features"]):
                decided = override_applies(case["key"], case["features"])
                self.assertEqual(case["expected"], decided)
                self.assertEqual(case["expected"], case["starlark"])

    def test_shell_configuration_carries_no_content_bound_setting(self) -> None:
        # The shell-assets probe stages no game: no autoload, main scene, content-bound
        # setting or unknown key naming a res:// path, authored or declared, while
        # context-bound and other settings stay.
        base = (
            'config_version=5\n[application]\nconfig/name="Demo"\n'
            'config/icon="res://icon.svg"\nrun/main_scene="res://main.tscn"\n'
            '[autoload]\nApp="*res://app.gd"\n[gui]\ntheme/custom="res://theme.tres"\n'
            '[addon_own]\nflag=true\nauthored="res://authored.tres"\n'
        )
        text = compose_project(
            base,
            {
                "addon_own/declared": '"res://declared.tres"',
                "addon_own/level": "3",
                "rendering/vrs/texture": '"res://vrs.png"',
            },
            {"Declared": "*res://declared.gd"},
            "res://declared.tscn",
            purpose="export",
            editor_plugins=["res://addons/a/plugin.cfg"],
            context_only=True,
        )
        for absent in (
            "main.tscn",
            "[autoload]",
            "theme.tres",
            "authored.tres",
            "declared",
            "vrs.png",
        ):
            self.assertNotIn(absent, text)
        for present in (
            'config/name="Demo"',
            "res://icon.svg",
            "flag=true",
            "level=3",
            "addons/a/plugin.cfg",
        ):
            self.assertIn(present, text)

    def test_program_entry_fails_for_each_left_out_setting(self) -> None:
        work = Path(tempfile.mkdtemp())
        base = work / "project.godot"
        base.write_text('config_version=5\n[gui]\ntheme/custom="res://theme.tres"\n')
        data = {"project_file": str(base), "kinds": KINDS, "members": []}
        failed = _run("left-out", work, data | {"program_entry": "//game:pack"})
        self.assertNotEqual(0, failed.returncode)
        self.assertIn(
            "//game:pack: Setting gui/theme/custom of the authored project.godot names "
            "res://theme.tres, which is no declared member of its deps",
            failed.stderr,
        )
        # Another operation leaves the setting out.
        self.assertEqual(
            0, _run("left-out", work, data | {"program_entry": ""}).returncode
        )
        self.assertEqual(
            [["gui/theme/custom", "res://theme.tres"]],
            json.loads((work / "left_out.json").read_text()),
        )

    def test_authored_custom_features_never_stay(self) -> None:
        # Custom features come only from the project's build settings.
        base = (
            '_custom_features="debug_tools"\nconfig_version=5\n[gui]\ntheme/custom=""\n'
        )
        for purpose in ("runtime", "import", "export", "editor"):
            with self.subTest(purpose=purpose):
                configured = compose_project(base, {}, {}, "", purpose=purpose)
                self.assertNotIn("_custom_features", configured)
                self.assertIn("config_version=5", configured)

    def test_omitted_contribution_also_removes_its_base_value(self) -> None:
        base = 'config_version=5\n[gui]\ntheme/custom=""\n'
        settings = {"gui/theme/custom": '"res://theme.tres"'}
        configured = compose_project(base, settings, {}, "", purpose="import")
        self.assertNotIn("theme/custom", configured)

    def test_export_purpose_keeps_runtime_configuration(self) -> None:
        base = (
            'config_version=5\n[application]\nrun/main_scene="res://main.tscn"\n'
            '[autoload]\nApp="*res://app.gd"\n'
            '[editor_plugins]\nenabled=PackedStringArray("res://addons/a/plugin.cfg")\n'
            '[gui]\ntheme/custom="res://theme.tres"\n'
        )
        exported = compose_project(
            base, {}, {"Extra": "*res://extra.gd"}, "", purpose="export"
        )
        self.assertNotIn("addons/a/plugin.cfg", exported)
        for present in (
            'run/main_scene="res://main.tscn"',
            'App="*res://app.gd"',
            'Extra="*res://extra.gd"',
            'theme/custom="res://theme.tres"',
        ):
            self.assertIn(present, exported)
        with self.assertRaises(ValueError):
            compose_project(base, {}, {}, "", purpose="unknown")

    def test_editor_and_export_purposes_enable_only_the_add_on_plugins(self) -> None:
        base = 'config_version=5\n[editor_plugins]\nenabled=PackedStringArray("res://authored/plugin.cfg")\n'
        plugins = ["res://addons/b/plugin.cfg", "res://addons/a/plugin.cfg"]
        for purpose in ("export", "editor"):
            with self.subTest(purpose=purpose):
                text = compose_project(
                    base, {}, {}, "", purpose=purpose, editor_plugins=plugins
                )
                self.assertNotIn("authored", text)
                self.assertIn(
                    'enabled=PackedStringArray("res://addons/a/plugin.cfg", '
                    '"res://addons/b/plugin.cfg")',
                    text,
                )
                self.assertEqual(1, text.count("[editor_plugins]"))
        for purpose in ("runtime", "import"):
            with self.subTest(purpose=purpose), self.assertRaises(ValueError):
                compose_project(base, {}, {}, "", purpose=purpose, editor_plugins=plugins)

    def test_probe_plugins_join_the_enabled_ones(self) -> None:
        probe = "res://probe/plugin.cfg"
        self.assertTrue(
            enable_plugins("config_version=5\n", [probe]).endswith(
                '\n[editor_plugins]\nenabled=PackedStringArray("res://probe/plugin.cfg")\n'
            )
        )
        for text in [
            'config_version=5\n\n[editor_plugins]\nenabled=PackedStringArray("res://a/plugin.cfg")\n\n[rendering]\nx=1\n',
            '[editor_plugins]\nenabled=PackedStringArray("res://a/plugin.cfg")\n',
        ]:
            with self.subTest(text=text):
                enabled = enable_plugins(text, [probe])
                self.assertIn(
                    'enabled=PackedStringArray("res://a/plugin.cfg", "res://probe/plugin.cfg")',
                    enabled,
                )
                self.assertEqual(1, enabled.count("[editor_plugins]"))
                self.assertEqual("x=1" in text, "x=1" in enabled)

    def test_import_purpose_keeps_overrides_the_editor_applies(self) -> None:
        base = (
            'config_version=5\n[rendering]\nmethod="forward_plus"\n'
            'method.mobile="mobile"\nmethod.integration_test="gl_compatibility"\n'
            "compression.editor=false\ncompression.android.macos=true\n"
        )
        settings = {"rendering/scale.ios": "2"}
        self.assertEqual(
            ["android", "editor", "integration_test", "ios", "macos", "mobile"],
            override_tags(base, settings),
        )
        configured = compose_project(
            base,
            settings,
            {},
            "",
            purpose="import",
            active_features={"editor", "macos"},
        )
        self.assertIn('method="forward_plus"', configured)
        self.assertIn("compression.editor=false", configured)
        self.assertIn("compression.android.macos=true", configured)
        for absent in ("method.mobile", "method.integration_test", "scale.ios"):
            self.assertNotIn(absent, configured)
        unknown = compose_project(base, settings, {}, "", purpose="import")
        self.assertIn('method.mobile="mobile"', unknown)
        exported = compose_project(
            base, settings, {}, "", purpose="export", active_features={"editor"}
        )
        self.assertIn('method.mobile="mobile"', exported)

    def test_import_configuration_keeps_only_unit_level_settings(self) -> None:
        # FR-003: the import purpose drops autoloads, editor plugins, the main scene,
        # settings naming files and overrides of features the import editor lacks, and
        # keeps every other setting, authored or contributed.
        base = (
            'config_version=5\n[application]\nconfig/name="Demo"\n'
            'run/main_scene="res://main.tscn"\nboot_splash/image="res://splash.png"\n'
            '[autoload]\nApp="*res://app.gd"\n'
            '[editor_plugins]\nenabled=PackedStringArray("res://addons/a/plugin.cfg")\n'
            '[gui]\ntheme/custom="res://theme.tres"\n'
            '[input]\njump={\n"deadzone": 0.5,\n"events": []\n}\n'
            '[rendering]\nmethod="forward_plus"\nmethod.mobile="mobile"\n'
            "textures/vram_compression/import_etc2_astc=true\n"
        )
        configured = compose_project(
            base,
            {
                "display/window/size/viewport_width": "640",
                "gui/theme/custom_font": '"res://font.ttf"',
            },
            {"Extra": "*res://extra.gd"},
            "res://other.tscn",
            purpose="import",
            active_features={"editor", "macos"},
        )
        kept = sorted(
            f"{section}/{key}" if section else key
            for _, section, key in statement_groups(configured)
            if key is not None
        )
        self.assertEqual(
            [
                "application/config/name",
                "config_version",
                "display/window/size/viewport_width",
                "input/jump",
                "rendering/method",
                "rendering/textures/vram_compression/import_etc2_astc",
            ],
            kept,
        )
        self.assertNotIn("[editor_plugins]", configured)

    def test_typed_literals(self) -> None:
        for value in [
            "true",
            "4",
            "-2.5e-3",
            "inf",
            "-inf",
            "inf_neg",
            "Vector2(-inf, nan)",
            '"text"',
            "Color(1, 0, 0)",
            'PackedStringArray("a", "b")',
            '{"keys": [1, false]}',
        ]:
            self.assertEqual(value, validate_literal(value))
        for value in [
            "",
            'true\n[autoload]\nInjected="res://bad.gd"',
            'load("res://bad.gd")',
            '"unterminated',
            "[1, 2",
            "true;another=1",
            "5 + 4",
            "false true",
            'Object(InputEventKey,"physical_keycode":65)',
            'Array[String](["a"])',
        ]:
            with self.assertRaises(ValueError, msg=value):
                validate_literal(value)

    def test_authored_autoloads_as_godot_writes_them(self) -> None:
        # Godot's editor writes an autoload by its UID where the file has one.
        base = (
            'config_version=5\n[application]\nrun/main_scene="res://main.tscn"\n'
            '[autoload]\nState="*res://state.gd"\n"Hud"="*uid://b3x7hud"\n'
            'Plain="res://plain.gd"\nState.mobile="*res://mobile.gd"\nOdd=4\n'
            '[other]\nState="res://not_an_autoload.gd"\n'
        )
        self.assertEqual(
            {
                "State": "*res://state.gd",
                "Hud": "*uid://b3x7hud",
                "Plain": "res://plain.gd",
            },
            authored_autoloads(base),
        )
        self.assertEqual({}, authored_autoloads("config_version=5\n"))

    def test_quoted_setting_keys_share_their_unquoted_identity(self) -> None:
        base = 'config_version=5\n[application]\n"config/name"="Base"\n"run/main_scene"="res://old.tscn"\n[rendering]\n"run/main_scene"="keep"\n"name=with=equals"="preserved"\n'
        text = compose_project(
            base, {"application/config/name": '"New"'}, {}, "res://new.tscn"
        )
        self.assertNotIn('"config/name"="Base"', text)
        self.assertNotIn('"run/main_scene"="res://old.tscn"', text)
        self.assertIn('config/name="New"', text)
        configured = compose_project(base, {}, {}, "", purpose="import")
        self.assertNotIn("res://old.tscn", configured)
        self.assertIn('"run/main_scene"="keep"', configured)
        self.assertIn('"name=with=equals"="preserved"', configured)

    def test_preserves_complex_authored_literals_outside_replacements(self) -> None:
        event = 'action={\n"deadzone": 0.5,\n"events": [Object(InputEventKey,"physical_keycode":65)]\n}\n'
        typed_array = 'values=Array[String](["a", "b"])\n'
        base = "config_version=5\n[input]\n" + event + "[rendering]\n" + typed_array
        for purpose in ("runtime", "import", "export"):
            with self.subTest(purpose=purpose):
                text = compose_project(
                    base,
                    {"application/config/name": '"New"'},
                    {},
                    "",
                    purpose=purpose,
                )
                self.assertIn(event, text)
                self.assertIn(typed_array, text)


_AUTHORED = """; authored comment
; Format:
;   param=value ; assign values to parameters
config_version=5

[application]

config/name="Demo"
config/icon="res://icon.svg"

[display]

window/size/viewport_width=640

[network]

limits/timeout=5
"""


class WriteBackTest(unittest.TestCase):
    def test_editor_changes_reach_authored_keys_in_place(self) -> None:
        edited = (
            _AUTHORED.replace('"Demo"', '"Renamed"')
            .replace('config/icon="res://icon.svg"\n', "")
            .replace(
                "viewport_width=640",
                "viewport_width=640\nwindow/size/viewport_height=480",
            )
            + '\n[input]\n\njump={\n"deadzone": 0.5,\n"events": []\n}\n'
        )
        result = write_back(_AUTHORED, _AUTHORED, edited, {})
        self.assertEqual(
            result.written,
            [
                "application/config/icon",
                "application/config/name",
                "display/window/size/viewport_height",
                "input/jump",
            ],
        )
        self.assertEqual(result.reported, [])
        self.assertEqual(
            result.text,
            "; authored comment\n; Format:\n;   param=value ; assign values to "
            "parameters\nconfig_version=5\n\n[application]\n\n"
            'config/name="Renamed"\n\n[display]\n\nwindow/size/viewport_width=640\n'
            "window/size/viewport_height=480\n\n[network]\n\nlimits/timeout=5\n\n"
            '[input]\n\njump={\n"deadzone": 0.5,\n"events": []\n}\n',
        )

    def test_composed_settings_and_plugins_are_reported(self) -> None:
        baseline = _AUTHORED + '\n[autoload]\n\nState="*res://state.gd"\n'
        edited = (
            baseline.replace("limits/timeout=5", "limits/timeout=9").replace(
                "state.gd", "other.gd"
            )
            + '\n[editor_plugins]\n\nenabled=PackedStringArray("res://addons/a/plugin.cfg")\n'
        )
        result = write_back(
            _AUTHORED,
            baseline,
            edited,
            {
                "network/limits/timeout": "//game:project",
                "autoload/State": "//state:state",
            },
        )
        self.assertEqual(result.text, _AUTHORED)
        self.assertEqual(result.written, [])
        self.assertEqual(
            result.reported,
            [
                "autoload/State is set by //state:state; change it there",
                (
                    "editor_plugins/enabled is set by the project's editor_plugins; "
                    "change it there"
                ),
                "network/limits/timeout is set by //game:project; change it there",
            ],
        )

    def test_authored_change_during_the_session_wins(self) -> None:
        authored = _AUTHORED.replace("640", "1024")
        edited = _AUTHORED.replace("640", "800")
        result = write_back(authored, _AUTHORED, edited, {})
        self.assertEqual(result.text, authored)
        self.assertEqual(len(result.reported), 1)
        self.assertIn("kept the authored value", result.reported[0])


if __name__ == "__main__":
    unittest.main()
