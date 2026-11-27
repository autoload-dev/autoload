import hashlib
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tools.editor_action import project as project_actions
from tools.editor_action.project import (
    import_base,
    import_resources,
    importable_suffixes,
    importer_mismatches,
    initialize,
)
from tools.inputs.originals import IMPORT_ARCHIVE, write_archive


class GodotActionsTest(unittest.TestCase):
    def test_import_archives_only_what_godot_added_or_altered(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            (base / "project.godot").write_text("config_version=5\n")
            results = base / "results"
            (results / ".godot/imported").mkdir(parents=True)
            names = ["rewritten", "altered", "untouched"]
            for name in names:
                (results / f".godot/imported/{name}.ctex").write_bytes(name.encode())
            (base / "dependency").mkdir()
            write_archive(
                results,
                [f".godot/imported/{name}.ctex" for name in names],
                base / "dependency" / IMPORT_ARCHIVE,
            )

            def editor(
                manifest: dict, execroot: Path, root: Path, work: Path, args: list[str]
            ) -> dict:
                imported = root / ".godot/imported"
                (imported / "rewritten.ctex").write_bytes(b"rewritten")
                (imported / "altered.ctex").write_bytes(b"reimported")
                (imported / "new.ctex").write_bytes(b"new")
                return {"facts": {"invalid": []}, "output": ""}

            output = base / "out" / IMPORT_ARCHIVE
            manifest = {
                "project_file": "project.godot",
                "member_resource_paths": {},
                "imports": ["dependency"],
                "outputs": [],
                "editor": "editor",
            }
            with mock.patch.object(project_actions, "run_action", editor):
                import_resources(manifest, output, base)
            with tarfile.open(output) as stream:
                self.assertEqual(
                    [".godot/imported/altered.ctex", ".godot/imported/new.ctex"],
                    stream.getnames(),
                )

    def test_an_import_keeps_no_result_of_the_importers_it_stages(self) -> None:
        # FR-017, FR-020: the importer's own assets import with its add-on, not again in
        # every unit whose import stages the importer.
        self.assertEqual(
            ".godot/imported/icon.svg-"
            + hashlib.md5(b"res://addons/md/icon.svg").hexdigest()
            + ".",
            import_base("addons/md/icon.svg"),
        )
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            (base / "project.godot").write_text("config_version=5\n")

            def editor(
                manifest: dict, execroot: Path, root: Path, work: Path, args: list[str]
            ) -> dict:
                (root / ".godot/imported").mkdir(parents=True)
                for path in ["notes.md", "addons/md/icon.svg"]:
                    for suffix in ["res", "md5"]:
                        (root / (import_base(path) + suffix)).write_bytes(b"x")
                return {"facts": {"invalid": []}, "output": ""}

            output = base / "out" / IMPORT_ARCHIVE
            manifest = {
                "project_file": "project.godot",
                "member_resource_paths": {},
                "imports": [],
                "outputs": ["notes.md"],
                "tools": ["addons/md/icon.svg", "addons/md/importer.gd"],
                "editor": "editor",
            }
            with mock.patch.object(project_actions, "run_action", editor):
                import_resources(manifest, output, base)
            with tarfile.open(output) as stream:
                self.assertEqual(
                    [import_base("notes.md") + "md5", import_base("notes.md") + "res"],
                    stream.getnames(),
                )

    def test_the_importer_probe_fails_on_a_suffix_the_declaration_lacks(self) -> None:
        # FR-018, US5 AS3: an importer for an undeclared suffix and a declared suffix
        # nothing converts each fail, naming the add-on and the suffix.
        importers = [
            {
                "label": "//addons:md",
                "suffixes": ["markdown", "md"],
                "scripts": ["res://addons/md/importer.gd"],
                "plugin": "res://addons/md/plugin.cfg",
                "native": False,
                "member_resource_paths": {},
            }
        ]
        records = {
            "--editor": {
                "facts": {
                    "suffixes": ["md", "png", "txt"],
                    "importers": [
                        {
                            "label": "//addons:md",
                            "suffixes": ["md", "TXT"],
                        }
                    ],
                }
            },
            "--script": {"facts": {"suffixes": ["png"]}},
        }
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            (base / "project.godot").write_text("config_version=5\n")
            manifest = {
                "project_file": "project.godot",
                "member_resource_paths": {},
                "imports": [],
                "importers": importers,
                "editor": "editor",
            }

            def editor(
                manifest: dict, execroot: Path, root: Path, work: Path, args: list[str]
            ) -> dict:
                return records[args[0]]

            with mock.patch.object(project_actions, "run_action", editor):
                with self.assertRaisesRegex(
                    RuntimeError,
                    "//addons:md registers an importer for the suffix 'txt'(.|\n)*"
                    "//addons:md declares the importer suffix 'markdown'",
                ):
                    importable_suffixes(manifest, base / "out", base)
                importers[0]["suffixes"] = ["md", "txt"]
                importable_suffixes(manifest, base / "out", base)
            self.assertEqual(
                ["md", "txt"], sorted(path.name for path in (base / "out").iterdir())
            )

    def test_extension_importers_are_the_suffixes_their_add_on_adds(self) -> None:
        # E10: Godot does not say which library registered an importer, so an add-on with
        # an extension contributes what the editor recognizes only with it staged; a
        # declared suffix Godot imports anyway cannot be told apart and is no mismatch.
        native = {
            "label": "//addons:native",
            "suffixes": ["png", "vox"],
            "native": True,
            "member_resource_paths": {"addons/native/native.gdextension": "x"},
        }
        self.assertEqual(
            [], importer_mismatches([native], {"//addons:native": {"vox"}}, {"png"})
        )
        self.assertEqual(
            [
                (
                    "//addons:native declares the importer suffix 'vox', "
                    "which none of its importers converts"
                )
            ],
            importer_mismatches([native], {}, {"png"}),
        )

    def test_an_import_fails_only_on_its_own_invalid_files(self) -> None:
        for invalid, fails in [(["other.png"], False), (["mine.png"], True)]:
            with self.subTest(invalid=invalid), tempfile.TemporaryDirectory() as temp:
                base = Path(temp)
                (base / "project.godot").write_text("config_version=5\n")
                record = {"facts": {"invalid": invalid}, "output": "importer said no"}
                manifest = {
                    "project_file": "project.godot",
                    "member_resource_paths": {},
                    "imports": [],
                    "outputs": ["mine.png"],
                    "editor": "editor",
                }
                with mock.patch.object(
                    project_actions, "run_action", return_value=record
                ):
                    if fails:
                        with self.assertRaisesRegex(
                            RuntimeError,
                            "could not import mine.png(.|\n)*importer said no",
                        ):
                            import_resources(
                                manifest, base / "out" / IMPORT_ARCHIVE, base
                            )
                    else:
                        import_resources(manifest, base / "out" / IMPORT_ARCHIVE, base)

    def test_initialize_accepts_a_project_without_resource_uids(self) -> None:
        # Godot writes no UID cache when no resource has a UID, as in an empty project.
        for written, fails in [
            ([".godot/global_script_class_cache.cfg"], False),
            ([".godot/uid_cache.bin"], True),
        ]:
            with self.subTest(written=written), tempfile.TemporaryDirectory() as temp:
                base = Path(temp)
                (base / "project.godot").write_text("config_version=5\n")

                def editor(
                    manifest: dict,
                    execroot: Path,
                    root: Path,
                    work: Path,
                    args: list[str],
                    written: list[str] = written,
                ) -> dict:
                    for relative in written:
                        (root / relative).parent.mkdir(parents=True, exist_ok=True)
                        (root / relative).write_text("cache")
                    return {"facts": {"invalid": []}, "output": "", "stopped": False}

                manifest = {
                    "project_file": "project.godot",
                    "member_resource_paths": {},
                    "imports": [],
                    "editor": "editor",
                }
                output = base / "out"
                with mock.patch.object(project_actions, "run_action", editor):
                    if fails:
                        with self.assertRaisesRegex(
                            RuntimeError, "global_script_class_cache.cfg"
                        ):
                            initialize(manifest, output, base)
                        continue
                    initialize(manifest, output, base)
                self.assertEqual(
                    [".godot/global_script_class_cache.cfg"],
                    [
                        path.relative_to(output).as_posix()
                        for path in output.rglob("*")
                        if path.is_file()
                    ],
                )


if __name__ == "__main__":
    unittest.main()
