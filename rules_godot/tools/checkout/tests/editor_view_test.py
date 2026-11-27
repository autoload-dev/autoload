"""Contract tests for editor views: layout, sync, write-back and reports."""

import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tools.checkout.editor import (
    EditorError,
    Layout,
    link_directories,
    open_editor,
    plan_layout,
    sync,
)
from tools.checkout.metadata_sync import (
    check_metadata,
    index_updates,
    list_sidecars,
    place_metadata,
)
from tools.tests.stub_program import write_stub_program

_AUTHORED = """config_version=5

[application]

config/name="Demo"

[display]

window/size/viewport_width=640
"""


class LinkDirectoriesTest(unittest.TestCase):
    def test_links_the_highest_directory_with_one_checkout_origin(self) -> None:
        linked = link_directories(
            {
                "levels/one.json": "game/levels/one.json",
                "levels/deep/two.json": "game/levels/deep/two.json",
                "main.gd": "game/main.gd",
            },
            set(),
        )
        self.assertEqual(linked, {"levels": "game/levels"})

    def test_mixed_renamed_and_generated_directories_are_not_linked(self) -> None:
        linked = link_directories(
            {
                "data/brand.json": "game/blue.json",
                "mixed/a.gd": "one/a.gd",
                "mixed/b.gd": "two/b.gd",
                "shared/a.gd": "game/shared/a.gd",
                "addons/x/plugin.cfg": "third/addon/plugin.cfg",
            },
            {"shared/version.json"},
        )
        self.assertEqual(linked, {"addons/x": "third/addon"})

    def test_never_links_the_workspace_root(self) -> None:
        self.assertEqual(link_directories({"levels/one.json": "one.json"}, set()), {})


class ViewTest(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)
        self.workspace = self.base / "workspace"
        self.runfiles = self.base / "runfiles"
        files = {
            "game/main.gd": "extends Node\n",
            "game/levels/one.json": "{}\n",
            "game/blue.json": '{"brand": "blue"}\n',
            "game/project.godot": _AUTHORED,
        }
        for path, text in files.items():
            self.write(self.workspace / path, text)
        self.write(self.workspace / ".bazelignore", ".godot-editor\n")
        self.write(self.runfiles / "version.json", "1\n")
        self.write(
            self.runfiles / "editor.project.godot",
            _AUTHORED + '\n[application]\nrun/main_scene="res://main.tscn"\n',
        )
        initialized = self.runfiles / "initialized"
        self.write(initialized / ".godot/uid_cache.bin", "cache")
        self.write(initialized / "main.gd.uid", "uid://main\n")
        self.write(initialized / "levels/one.json.uid", "uid://one\n")
        self.write(self.runfiles / "imports", "")
        # What the project's sidecar list action writes for these files.
        self.sidecars = list_sidecars(
            {
                "main.gd": ["game/main.gd", "//game:project"],
                "levels/one.json": ["game/levels/one.json", "//game:levels"],
                "data/brand.json": ["game/blue.json", "//game:brand"],
            },
            [],
            [str(initialized)],
        )
        self.write(self.runfiles / "sidecars.json", json.dumps(self.sidecars))

    @staticmethod
    def write(path: Path, text: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def runfile(self, short_path: str) -> Path:
        return self.runfiles / short_path

    def manifest(self, editor: str) -> dict:
        write_stub_program(self.runfiles / "editor", editor)
        return {
            "label": "//game:edit",
            "workspace": "",
            "editor": "editor",
            "views": ".godot-editor",
            "view": ".godot-editor/game/edit",
            "env": {"EDITOR_TEST": "1"},
            "project_file": "editor.project.godot",
            "authored_project_file": "game/project.godot",
            "composed_settings": {"application/run/main_scene": "//game:project"},
            "checkout": {
                "main.gd": "game/main.gd",
                "levels/one.json": "game/levels/one.json",
                "data/brand.json": "game/blue.json",
            },
            "metadata": "sidecars.json",
            "write_sidecars": True,
            "copies": {"data/version.json": "version.json"},
            "imports": "imports",
            "initialized": "initialized",
        }

    def open(self, editor: str) -> tuple[int, str]:
        output = io.StringIO()
        with contextlib.redirect_stderr(output):
            code = open_editor(
                self.manifest(editor), self.workspace, ["--arg"], self.runfile
            )
        return code, output.getvalue()

    @property
    def view(self) -> Path:
        return self.workspace / ".godot-editor/game/edit"

    def test_view_links_sources_and_copies_build_files(self) -> None:
        code, output = self.open("import sys; sys.exit(3)\n")
        self.assertEqual(code, 3)
        view = self.view
        self.assertEqual(
            Path(os.readlink(view / "levels")), self.workspace / "game/levels"
        )
        self.assertEqual(
            Path(os.readlink(view / "main.gd")), self.workspace / "game/main.gd"
        )
        self.assertEqual(
            Path(os.readlink(view / "data/brand.json")), self.workspace / "game/blue.json"
        )
        # Root may write any file, so the mode, not access, tells read-only copies.
        self.assertFalse((view / "data/version.json").stat().st_mode & 0o222)
        self.assertEqual((view / "main.gd.uid").read_text(), "uid://main\n")
        self.assertEqual((view / ".godot/uid_cache.bin").read_text(), "cache")
        # Missing sidecars are written beside their files before the editor opens.
        self.assertEqual(
            (self.workspace / "game/levels/one.json.uid").read_text(), "uid://one\n"
        )
        self.assertEqual(
            (self.workspace / "game/main.gd.uid").read_text(), "uid://main\n"
        )
        # The view links a sidecar written beside a linked file.
        self.assertEqual(
            Path(os.readlink(view / "main.gd.uid")), self.workspace / "game/main.gd.uid"
        )
        self.assertIn(
            "wrote game/levels/one.json.uid; commit it and declare it in "
            "//game:levels as res://levels/one.json.uid",
            output,
        )
        self.assertEqual(
            (self.workspace / ".godot-editor/.gitignore").read_text()[-2:], "*\n"
        )

    def test_editor_edits_checkout_and_settings_are_written_back(self) -> None:
        code, output = self.open(
            "import os, sys\n"
            "from pathlib import Path\n"
            "assert sys.argv[1:3] + sys.argv[4:] == ['--editor', '--path', '--arg']\n"
            "assert os.path.samefile(sys.argv[3], os.getcwd())\n"
            "assert os.environ['EDITOR_TEST'] == '1'\n"
            "Path('main.gd').write_text('extends Node2D\\n')\n"
            "Path('levels/two.json').write_text('{}\\n')\n"
            "Path('levels/one.json.uid.uid').write_text('uid://stray\\n')\n"
            "Path('notes.gd').write_text('extends Node\\n')\n"
            "Path('data/brand.json').rename('data/moved.json')\n"
            "text = Path('project.godot').read_text()\n"
            "text = text.replace('\"Demo\"', '\"Renamed\"')\n"
            "text = text.replace('res://main.tscn', 'res://other.tscn')\n"
            "Path('project.godot').write_text(text)\n"
        )
        self.assertEqual(code, 0, output)
        game = self.workspace / "game"
        self.assertEqual((game / "main.gd").read_text(), "extends Node2D\n")
        self.assertTrue((game / "levels/two.json").is_file())
        self.assertTrue((game / "blue.json").is_file())
        authored = (game / "project.godot").read_text()
        self.assertIn('config/name="Renamed"', authored)
        self.assertNotIn("main_scene", authored)
        self.assertIn("wrote application/config/name to game/project.godot", output)
        self.assertIn(
            "application/run/main_scene is set by //game:project; change it there", output
        )
        self.assertIn(
            "res://notes.gd exists only in the view; move it to game/ and declare it",
            output,
        )
        self.assertIn("res://data/moved.json links to", output)
        self.assertIn("res://data/brand.json was moved or deleted in the editor", output)

        # The next run lists what is still undeclared and keeps editor files.
        code, output = self.open("")
        self.assertIn(
            "res://levels/two.json is in a linked directory but not in //game:edit",
            output,
        )
        # Godot writes no sidecar beside a sidecar, so this one is undeclared.
        self.assertIn(
            "res://levels/one.json.uid.uid is in a linked directory but not in //game:edit",
            output,
        )
        self.assertTrue((self.view / "notes.gd").is_file())
        self.assertNotIn("wrote application/config/name", output)

    def test_settings_changed_on_both_sides_keep_the_authored_value(self) -> None:
        self.open(
            "from pathlib import Path\n"
            "text = Path('project.godot').read_text().replace('640', '800')\n"
            "Path('project.godot').write_text(text)\n"
            "authored = Path('../../../game/project.godot')\n"
            "authored.write_text(authored.read_text().replace('640', '1024'))\n"
        )
        authored = (self.workspace / "game/project.godot").read_text()
        self.assertIn("viewport_width=1024", authored)

    def test_requires_bazel_to_ignore_views(self) -> None:
        (self.workspace / ".bazelignore").write_text("")
        with self.assertRaisesRegex(EditorError, "Add the line .godot-editor"):
            self.open("")

    def relinked_layouts(self) -> tuple[Layout, Layout]:
        """levels/ with a generated file, so file links; then without, so linked."""
        levels = {"levels/one.json": "game/levels/one.json"}
        generated = {"levels/version.json": self.runfile("version.json")}
        return plan_layout(levels, generated, {}), plan_layout(levels, {}, {})

    def test_resync_replaces_file_links_with_a_directory_link(self) -> None:
        view = self.base / "view"
        view.mkdir()
        first, second = self.relinked_layouts()
        record = sync(view, self.workspace, first, {})
        self.assertTrue((view / "levels").is_dir())
        self.assertFalse((view / "levels").is_symlink())
        sync(view, self.workspace, second, record)
        self.assertTrue((view / "levels").is_symlink())

    def test_resync_reads_unchanged_copies_only_once(self) -> None:
        view = self.base / "view"
        layout = plan_layout({}, {"data/version.json": self.runfile("version.json")}, {})
        record = sync(view, self.workspace, layout, {})
        with mock.patch("tools.checkout.editor.same_content") as same_content:
            sync(view, self.workspace, layout, record)
        same_content.assert_not_called()
        # Bazel replaces a rebuilt output with a new file.
        rebuilt = self.runfiles / "version.json.new"
        self.write(rebuilt, "2\n")
        rebuilt.replace(self.runfiles / "version.json")
        sync(view, self.workspace, layout, record)
        self.assertEqual((view / "data/version.json").read_text(), "2\n")

    def test_resync_refuses_to_hide_files_created_in_the_view(self) -> None:
        view = self.base / "view"
        first, second = self.relinked_layouts()
        record = sync(view, self.workspace, first, {})
        (view / "levels/new.json").write_text("{}\n")
        with self.assertRaisesRegex(EditorError, "levels/new.json"):
            sync(view, self.workspace, second, record)

    def test_editor_leaves_scene_node_ids_to_godot_metadata_sync(self) -> None:
        scene = '[gd_scene format=3]\n\n[node name="Main" type="Node"]\n'
        self.write(self.workspace / "game/main.tscn", scene)
        entry = {
            "kind": "node_ids",
            "path": "main.tscn",
            "workspace": "game/main.tscn",
            "owner": "//game:project",
        }
        self.write(self.runfiles / "sidecars.json", json.dumps(self.sidecars + [entry]))
        code, output = self.open("")
        self.assertEqual(code, 0, output)
        self.assertEqual(scene, (self.workspace / "game/main.tscn").read_text())
        self.assertNotIn("main.tscn", output)

    def test_editor_only_names_missing_sidecars_without_write_sidecars(self) -> None:
        manifest = self.manifest("")
        manifest["write_sidecars"] = False
        output = io.StringIO()
        with contextlib.redirect_stderr(output):
            open_editor(manifest, self.workspace, [], self.runfile)
        self.assertFalse((self.workspace / "game/levels/one.json.uid").exists())
        self.assertIn(
            "game/levels/one.json.uid is missing; Godot writes its own when it finds "
            "the file",
            output.getvalue(),
        )

    def test_sidecar_list_names_each_file_and_its_owner(self) -> None:
        self.assertEqual(
            self.sidecars,
            [
                {
                    "kind": "sidecar",
                    "path": "levels/one.json.uid",
                    "workspace": "game/levels/one.json.uid",
                    "owner": "//game:levels",
                    "content": "uid://one\n",
                },
                {
                    "kind": "sidecar",
                    "path": "main.gd.uid",
                    "workspace": "game/main.gd.uid",
                    "owner": "//game:project",
                    "content": "uid://main\n",
                },
            ],
        )

    def test_sidecars_are_written_beside_their_files_once(self) -> None:
        self.write(self.workspace / "game/main.gd.uid", "uid://authored\n")
        output = io.StringIO()
        with contextlib.redirect_stderr(output):
            missing = place_metadata(self.sidecars, self.workspace, write=False)
            self.assertEqual(
                [sidecar["path"] for sidecar in missing], ["levels/one.json.uid"]
            )
            self.assertEqual(check_metadata(self.sidecars, "@@//game:metadata"), 1)
            self.assertEqual(check_metadata([], "@@//game:metadata"), 0)
            place_metadata(self.sidecars, self.workspace, write=True)
        self.assertIn(
            "game/levels/one.json.uid is missing or not declared; write it with "
            "bazel run //game:metadata and declare it in //game:levels as "
            "res://levels/one.json.uid",
            output.getvalue(),
        )
        self.assertEqual(
            (self.workspace / "game/levels/one.json.uid").read_text(), "uid://one\n"
        )
        self.assertIn(
            "wrote game/levels/one.json.uid; commit it and declare it in "
            "//game:levels as res://levels/one.json.uid",
            output.getvalue(),
        )
        # An existing file is never replaced, only named until it is declared.
        self.assertEqual(
            (self.workspace / "game/main.gd.uid").read_text(), "uid://authored\n"
        )
        self.assertIn(
            "game/main.gd.uid is not declared; declare it in //game:project as "
            "res://main.gd.uid",
            output.getvalue(),
        )

    def test_index_entries_update_checkout_files_when_written(self) -> None:
        scene = (
            "[gd_scene format=3]\r\n\r\n"
            '[ext_resource type="Script" path="res://main.gd" id="1"]\r\n\r\n'
            '[node name="Main" type="Node"]\r\n'
        )
        self.write(self.workspace / "game/main.tscn", scene)
        index = {
            "node_ids": {
                "main.tscn": {"issues": ["Main"]},
                "external.tscn": {"issues": ["Other"]},
            },
            "resource_uids": {
                "main.tscn": {
                    "issues": ["res://main.gd (missing)"],
                    "uids": {"main.gd": "uid://main"},
                }
            },
        }
        checkout = {"main.tscn": ["game/main.tscn", "//game:project"]}
        updates = index_updates(checkout, index, ["node_ids", "resource_uids"])
        # Files outside the checkout are the build's to complete.
        self.assertEqual(
            [("node_ids", "main.tscn"), ("resource_uids", "main.tscn")],
            [(update["kind"], update["path"]) for update in updates],
        )
        output = io.StringIO()
        with contextlib.redirect_stderr(output):
            self.assertEqual(check_metadata(updates, "@@//game:metadata"), 0)
            self.assertEqual(
                check_metadata(updates, "@@//game:metadata", required={"resource_uids"}),
                1,
            )
            self.assertEqual(
                updates, place_metadata(updates, self.workspace, write=False)
            )
            self.assertEqual([], place_metadata(updates, self.workspace, write=True))
        self.assertIn(
            "The checkout has references without the UID of the file they name:\n"
            "  res://main.tscn: res://main.gd (missing)\n"
            "Commit the values with bazel run //game:metadata.",
            output.getvalue(),
        )
        self.assertNotIn("scene nodes without unique_id", output.getvalue())
        written = (self.workspace / "game/main.tscn").read_bytes().decode()
        self.assertIn('uid="uid://main" path="res://main.gd"', written)
        self.assertIn("unique_id=", written)
        self.assertIn("\r\n", written)

    def test_view_belongs_to_one_target(self) -> None:
        code, output = self.open("")
        self.assertEqual(code, 0, output)
        record = json.loads((self.view / ".godot/rules_godot/view.json").read_text())
        self.assertEqual(record["label"], "//game:edit")
        manifest = self.manifest("")
        manifest["label"] = "//other:edit"
        with self.assertRaisesRegex(EditorError, "belongs to //game:edit"):
            open_editor(manifest, self.workspace, [], self.runfile)


if __name__ == "__main__":
    unittest.main()
