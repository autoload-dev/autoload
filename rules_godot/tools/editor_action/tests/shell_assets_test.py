import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tools.editor_action import export, shell_assets


class ShellAssetsTest(unittest.TestCase):
    """The shell probe's outputs, from the facts and images a stub Godot records."""

    def setUp(self) -> None:
        self.base = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.enterContext(
            mock.patch.object(
                export, "export_lock", return_value=self.base / "export.lock"
            )
        )
        (self.base / "project.godot").write_text("config_version=5\n")

    def shell(self, spec: dict, rendered: list[str], copied: dict[str, str]) -> dict:
        """Run the probe with a Godot that renders and stages the named images."""
        images: list[dict] = []

        def join(root: Path, work: Path, operation: str, parameters: dict) -> None:
            images.extend(parameters["images"])

        def godot(
            manifest: dict, execroot: Path, root: Path, work: Path, args: list[str]
        ) -> dict:
            for image in images:
                if image["name"] in rendered:
                    Path(image["output"]).parent.mkdir(parents=True, exist_ok=True)
                    Path(image["output"]).write_bytes(image["name"].encode())
            for source in copied.values():
                staged = root / source.removeprefix("res://")
                staged.parent.mkdir(parents=True, exist_ok=True)
                staged.write_text("copied\n")
            facts = {"options": {"a": 1}, "rendered": rendered, "copied": copied}
            return {"facts": facts, "output": "Godot's output"}

        output = self.base / "facts.json"
        with (
            mock.patch.object(shell_assets, "join_action", join),
            mock.patch.object(export, "run_action", godot),
        ):
            shell_assets.shell_assets(self.manifest(spec), output, self.base)
        return json.loads(output.read_text())

    def manifest(self, spec: dict) -> dict:
        return {
            "project_file": "project.godot",
            "member_resource_paths": {},
            "editor": "editor",
            "version": "4.7.2",
            "preset_platform": "Linux",
            "variant": "release",
            "shell": {"versions": {}} | spec,
        }

    def test_rendered_sizes_become_one_icns_file(self) -> None:
        spec = {
            "directories": ["icons"],
            "icns": "icons/icon.icns",
            "images": [
                {"name": "icon_16", "sources": [], "size": 16},
                {"name": "icon_32", "sources": [], "size": 32},
                {"name": "icon_64", "sources": [], "size": 64},
            ],
        }
        facts = self.shell(spec, ["icon_16", "icon_32"], {})
        self.assertEqual({"options": {"a": 1}}, facts)
        self.assertEqual(
            shell_assets.icns({16: b"icon_16", 32: b"icon_32"}),
            (self.base / "icons/icon.icns").read_bytes(),
        )

    def test_a_copied_icns_file_replaces_the_rendered_sizes(self) -> None:
        spec = {
            "icns": "icon.icns",
            "images": [{"name": "icon_16", "sources": [], "size": 16}],
        }
        self.shell(spec, ["icon_16"], {"icon_16": "res://art/icon.icns"})
        self.assertEqual("copied\n", (self.base / "icon.icns").read_text())

    def test_copied_images_and_the_adaptive_icon_take_their_outputs(self) -> None:
        spec = {
            "directories": ["res", "splash"],
            "images": [
                {
                    "name": "mipmap/icon_foreground.webp",
                    "output": "res/fg.webp",
                    "sources": [],
                },
                {
                    "name": "mipmap/icon_monochrome.webp",
                    "output": "res/mono.webp",
                    "sources": [],
                },
                {
                    "name": "drawable/splash_icon.webp",
                    "output": "splash/splash_icon.webp",
                    "sources": [],
                    "copy": {"extension": ".xml", "output": "splash/splash_icon.xml"},
                },
            ],
            "adaptive_icon": {
                "output": "res/mipmap-anydpi-v26/icon.xml",
                "foreground": "mipmap/icon_foreground.webp",
                "monochrome": "mipmap/icon_monochrome.webp",
            },
        }
        copied = {"drawable/splash_icon.webp": "res://splash.xml"}
        for monochrome in [True, False]:
            rendered = ["mipmap/icon_foreground.webp"] + (
                ["mipmap/icon_monochrome.webp"] if monochrome else []
            )
            with self.subTest(monochrome=monochrome):
                self.shell(spec, rendered, copied)
                self.assertEqual(
                    "copied\n", (self.base / "splash/splash_icon.xml").read_text()
                )
                self.assertEqual(
                    b"mipmap/icon_foreground.webp",
                    (self.base / "res/fg.webp").read_bytes(),
                )
                icon = (self.base / "res/mipmap-anydpi-v26/icon.xml").read_text()
                self.assertIn(
                    '<foreground android:drawable="@mipmap/icon_foreground"/>', icon
                )
                self.assertEqual(monochrome, "icon_monochrome" in icon)

    def test_a_required_image_godot_did_not_render_fails(self) -> None:
        spec = {
            "images": [
                {"name": "a.png", "output": "a.png", "sources": [], "required": True},
                {"name": "b.png", "output": "b.png", "sources": [], "required": True},
                {"name": "c.png", "output": "c.png", "sources": []},
            ],
        }
        with self.assertRaisesRegex(
            RuntimeError, "Godot rendered no image for b.png; the project"
        ):
            self.shell(spec, ["a.png"], {})

    def test_a_probe_without_facts_fails_with_godots_output(self) -> None:
        record = {"facts": {}, "output": "Godot's output"}
        with (
            mock.patch.object(shell_assets, "join_action"),
            mock.patch.object(export, "run_action", return_value=record),
            self.assertRaisesRegex(
                RuntimeError,
                "recorded no export facts; its script failed:\nGodot's output",
            ),
        ):
            shell_assets.shell_assets(
                self.manifest({"images": []}), self.base / "facts.json", self.base
            )


if __name__ == "__main__":
    unittest.main()
