import json
import tarfile
import tempfile
import unittest
from pathlib import Path

from tools.inputs.manifest import add_resource_path_manifests, resource_path
from tools.inputs.mapped_paths import resolver
from tools.inputs.originals import (
    IMPORT_ARCHIVE,
    copy_file,
    executable,
    same_content,
    write_archive,
)
from tools.staging.files import validate_staged_paths
from tools.staging.project import stage


class StagingTest(unittest.TestCase):
    def test_extensions_are_registered_before_cold_editor_start(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            (base / "project.godot").write_text("config_version=5\n")
            (base / "extension").write_text(
                '[configuration]\nentry_symbol="example_init"\n'
            )
            root = base / "project"
            root.mkdir()
            stage(
                {
                    "project_file": "project.godot",
                    "member_resource_paths": {
                        "native/b.gdextension": "extension",
                        "native/a.gdextension": "extension",
                    },
                },
                root,
                base,
            )
            self.assertEqual(
                (root / ".godot/extension_list.cfg").read_text(),
                "res://native/a.gdextension\nres://native/b.gdextension\n",
            )

    def test_staged_copies_keep_the_executable_bit(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            handler = root / "crash_handler"
            handler.write_bytes(b"handler")
            handler.chmod(0o555)
            notice = root / "notice.txt"
            notice.write_bytes(b"notice")
            copy_file(handler, root / "staged/crash_handler")
            copy_file(notice, root / "staged/notice.txt")
            self.assertTrue(executable(root / "staged/crash_handler"))
            self.assertFalse(executable(root / "staged/notice.txt"))
            member = tarfile.TarInfo("crash_handler")
            member.mode = 0o755
            self.assertTrue(executable((root / "unit.tar", member)))
            self.assertFalse(executable(b"bytes"))

    def test_resource_identities_reject_escaping_paths(self) -> None:
        for path in ["../x", "/x", "a/../b", "a//b", "res://x", "a\\b", ""]:
            with self.subTest(path=path), self.assertRaises(ValueError):
                resource_path(path)
        self.assertEqual(resource_path("generated/a.tres"), "generated/a.tres")

    def test_staging_rejects_case_and_unicode_aliases_before_copying(self) -> None:
        for paths in [
            ("A.gd", "a.gd"),
            ("Assets/a.gd", "assets/b.gd"),
            ("a", "a/b"),
            ("caf\u00e9/a.gd", "cafe\u0301/b.gd"),
        ]:
            with (
                self.subTest(paths=paths),
                self.assertRaisesRegex(ValueError, "Conflicting"),
            ):
                validate_staged_paths({path: "input" for path in paths})
        validate_staged_paths({"a/a.gd": "one", "a/b.gd": "two"})

    def test_overlapping_imports_must_have_identical_content(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            (base / "project.godot").write_text("config_version=5\n")
            for name, content in [("one", "a"), ("two", "b")]:
                (base / name / ".godot/imported").mkdir(parents=True)
                (base / name / ".godot/imported/x.ctex").write_text(content)
            root = base / "staged"
            root.mkdir()
            with self.assertRaisesRegex(ValueError, "Conflicting import results"):
                stage(
                    {
                        "project_file": "project.godot",
                        "member_resource_paths": {},
                        "imports": ["one", "two"],
                    },
                    root,
                    base,
                )

    def test_cached_import_cannot_replace_an_authored_uid(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            (base / "project.godot").write_text("config_version=5\n")
            (base / "script.gd").write_text("extends Node\n")
            (base / "script.gd.uid").write_text("uid://authored\n")
            (base / "cached").mkdir()
            cached_uid = base / "cached/script.gd.uid"
            cached_uid.write_text("uid://generated\n")
            manifest = {
                "project_file": "project.godot",
                "member_resource_paths": {
                    "script.gd": "script.gd",
                    "script.gd.uid": "script.gd.uid",
                },
                "imports": ["cached"],
            }
            root = base / "staged"
            root.mkdir()
            with self.assertRaisesRegex(
                ValueError, "Cached import UID conflicts with authored sidecar"
            ):
                stage(manifest, root, base)
            cached_uid.write_text("uid://authored")
            stage(manifest, root, base)
            self.assertEqual("uid://authored", (root / "script.gd.uid").read_text())

    def test_cached_import_aliases_are_rejected_before_copying(self) -> None:
        aliases = [
            ("script.gd.UID", "script.gd.uid"),
            ("Assets/script.gd.uid", "assets/script.gd.uid"),
            ("caf\u00e9/script.gd.uid", "cafe\u0301/script.gd.uid"),
        ]
        for authored, cached in aliases:
            with (
                self.subTest(authored=authored, cached=cached),
                tempfile.TemporaryDirectory() as temp,
            ):
                base = Path(temp)
                (base / "project.godot").write_text("config_version=5\n")
                (base / "authored_uid").write_text("uid://authored\n")
                cached_uid = base / "cached" / cached
                cached_uid.parent.mkdir(parents=True)
                cached_uid.write_text("uid://generated\n")
                root = base / "staged"
                root.mkdir()
                manifest = {
                    "project_file": "project.godot",
                    "member_resource_paths": {authored: "authored_uid"},
                    "imports": ["cached"],
                }
                with self.assertRaisesRegex(
                    ValueError, "Conflicting portable Godot paths"
                ):
                    stage(manifest, root, base)
                self.assertEqual([], list(root.iterdir()))

    def test_cached_import_results_cannot_alias_each_other(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            (base / "project.godot").write_text("config_version=5\n")
            for result, filename in [
                ("one", ".godot/imported/FILE.ctex"),
                ("two", ".godot/imported/file.ctex"),
            ]:
                cached = base / result / filename
                cached.parent.mkdir(parents=True)
                cached.write_text("payload")
            root = base / "staged"
            root.mkdir()
            with self.assertRaisesRegex(ValueError, "Conflicting portable Godot paths"):
                stage(
                    {
                        "project_file": "project.godot",
                        "member_resource_paths": {},
                        "imports": ["one", "two"],
                    },
                    root,
                    base,
                )
            self.assertEqual([], list(root.iterdir()))

    def test_cached_imports_can_enrich_the_same_authored_import_sidecar(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            (base / "project.godot").write_text("config_version=5\n")
            (base / "authored_import").write_text('[remap]\nimporter="texture"\n')
            enriched = (
                '[remap]\nimporter="texture"\npath="res://.godot/imported/image.ctex"\n'
            )
            for tree in ["one", "two"]:
                (base / tree).mkdir()
                (base / tree / "image.png.import").write_text(enriched)
            root = base / "staged"
            root.mkdir()
            stage(
                {
                    "project_file": "project.godot",
                    "member_resource_paths": {"image.png.import": "authored_import"},
                    "imports": ["one", "two"],
                },
                root,
                base,
            )
            self.assertEqual(enriched, (root / "image.png.import").read_text())

    def test_unit_archives_are_deterministic_and_staged_like_import_results(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            (base / "project.godot").write_text("config_version=5\n")
            results = base / "results"
            (results / ".godot/imported").mkdir(parents=True)
            (results / ".godot/imported/icon.ctex").write_bytes(b"texture")
            (results / "icon.svg.import").write_text("[remap]\n")
            for name in ("one", "two"):
                (base / name).mkdir()
                write_archive(
                    results,
                    [".godot/imported/icon.ctex", "icon.svg.import"],
                    base / name / IMPORT_ARCHIVE,
                )
            self.assertEqual(
                (base / "one" / IMPORT_ARCHIVE).read_bytes(),
                (base / "two" / IMPORT_ARCHIVE).read_bytes(),
            )
            # A unit without importable files leaves an empty import result.
            (base / "empty").mkdir()
            root = base / "project"
            root.mkdir()
            stage(
                {
                    "project_file": "project.godot",
                    "member_resource_paths": {},
                    "imports": ["one", "empty"],
                },
                root,
                base,
            )
            self.assertEqual(
                (root / ".godot/imported/icon.ctex").read_bytes(), b"texture"
            )
            self.assertEqual((root / "icon.svg.import").read_text(), "[remap]\n")

    def test_archive_entries_must_be_regular_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            (base / "project.godot").write_text("config_version=5\n")
            (base / "linked").mkdir()
            with tarfile.open(base / "linked" / IMPORT_ARCHIVE, "w") as stream:
                link = tarfile.TarInfo(".godot/imported/icon.ctex")
                link.type, link.linkname = tarfile.SYMTYPE, "/etc/passwd"
                stream.addfile(link)
            root = base / "project"
            root.mkdir()
            with self.assertRaisesRegex(ValueError, "Unexpected archive entry"):
                stage(
                    {
                        "project_file": "project.godot",
                        "member_resource_paths": {},
                        "imports": ["linked"],
                    },
                    root,
                    base,
                )

    def test_the_importer_probe_enables_the_importers_it_stages(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            (base / "project.godot").write_text("config_version=5\n")
            root = base / "project"
            root.mkdir()
            stage(
                {
                    "project_file": "project.godot",
                    "member_resource_paths": {},
                    "editor_plugins": ["res://addons/md/plugin.cfg"],
                },
                root,
                base,
            )
            self.assertIn(
                'enabled=PackedStringArray("res://addons/md/plugin.cfg")',
                (root / "project.godot").read_text(),
            )

    def test_an_import_sets_the_import_settings_of_the_importers_it_stages(self) -> None:
        # D26: the import settings of an importer reach only the processes staging it,
        # beside the plugins the staged project.godot already enables.
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            (base / "project.godot").write_text(
                'config_version=5\n\n[editor_plugins]\nenabled=PackedStringArray("res://addons/a/plugin.cfg")\n'
            )
            root = base / "project"
            root.mkdir()
            stage(
                {
                    "project_file": "project.godot",
                    "member_resource_paths": {},
                    "editor_plugins": ["res://addons/md/plugin.cfg"],
                    "settings": {"md_importer/heading": '"#"'},
                },
                root,
                base,
            )
            text = (root / "project.godot").read_text()
            self.assertIn('heading="#"', text)
            self.assertIn(
                'enabled=PackedStringArray("res://addons/a/plugin.cfg", "res://addons/md/plugin.cfg")',
                text,
            )

    def test_resource_path_manifests_merge_unless_they_conflict(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            for name, resource_paths in [
                ("one", {"a.gd": "x/a.gd"}),
                ("two", {"a.gd": "x/a.gd", "b.gd": "x/b.gd"}),
                ("other", {"a.gd": "y/a.gd"}),
            ]:
                (base / name).write_text(json.dumps(resource_paths))
            manifest = {"project_file": "project.godot"}
            add_resource_path_manifests(
                manifest, [base / "one", base / "two"], resolver([])
            )
            self.assertEqual(
                {"a.gd": "x/a.gd", "b.gd": "x/b.gd"}, manifest["member_resource_paths"]
            )
            with self.assertRaisesRegex(
                ValueError, "Conflicting staged sources for a.gd"
            ):
                add_resource_path_manifests(manifest, [base / "other"], resolver([]))

    def test_staging_points_references_at_the_files_uids(self) -> None:
        scene = (
            "[gd_scene format=3]\n\n"
            '[ext_resource type="Script" uid="uid://stale" path="res://main.gd" id="1"]\n'
        )
        expected = scene.replace("uid://stale", "uid://main")
        for assign, staged_scene in [(["resource_uids"], expected), ([], scene)]:
            with self.subTest(assign=assign), tempfile.TemporaryDirectory() as temp:
                base = Path(temp)
                (base / "project.godot").write_text("config_version=5\n")
                (base / "main.tscn").write_text(scene)
                (base / "main.gd").write_text("extends Node\n")
                (base / "main.gd.uid").write_text("uid://main\n")
                root = base / "project"
                root.mkdir()
                (base / "index.json").write_text(
                    json.dumps(
                        {
                            "resource_uids": {
                                "main.tscn": {"uids": {"main.gd": "uid://main"}}
                            }
                        }
                    )
                )
                originals = stage(
                    {
                        "project_file": "project.godot",
                        "member_resource_paths": {
                            path: path for path in ["main.tscn", "main.gd", "main.gd.uid"]
                        },
                        "metadata_index": {"path": "index.json", "assign": assign},
                    },
                    root,
                    base,
                )
                self.assertEqual(staged_scene, (root / "main.tscn").read_text())
                self.assertEqual(scene, (base / "main.tscn").read_text())
                # Godot's import scan compares against these; the update is not its output.
                self.assertTrue(same_content(root / "main.tscn", originals["main.tscn"]))


if __name__ == "__main__":
    unittest.main()
