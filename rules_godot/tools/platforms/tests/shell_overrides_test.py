"""How shell defaults yield to the files an application supplies for the same slot."""

import plistlib
import tempfile
import unittest
from pathlib import Path

from tools.platforms import shell_overrides


class ShellOverridesTest(unittest.TestCase):
    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)

    def test_resource_keys_add_implied_versions(self) -> None:
        key = shell_overrides.resource_key
        self.assertEqual(
            key(Path("res/mipmap-xxxhdpi/icon.png")), "mipmap-xxxhdpi-v4/icon"
        )
        self.assertEqual(
            key(Path("mipmap-xxxhdpi-v4/icon.webp")), "mipmap-xxxhdpi-v4/icon"
        )
        self.assertEqual(
            key(Path("res/mipmap-anydpi/icon.xml")), "mipmap-anydpi-v21/icon"
        )
        self.assertEqual(key(Path("res/mipmap/icon.png")), "mipmap/icon")
        self.assertEqual(key(Path("res/drawable/a.9.png")), "drawable/a")

    def test_resources_yield_by_directory_and_name(self) -> None:
        source = self.root / "shell"
        for path in [
            "mipmap-xxxhdpi-v4/icon.webp",
            "mipmap-xxxhdpi-v4/icon_foreground.webp",
            "mipmap-anydpi-v26/icon.xml",
            "mipmap/icon.webp",
        ]:
            (source / path).parent.mkdir(parents=True, exist_ok=True)
            (source / path).write_text(path)
        output = self.root / "yielded"
        shell_overrides.copy_resources(
            source,
            output,
            [
                Path("res/mipmap-xxxhdpi/icon.png"),
                Path("res/mipmap-anydpi-v26/icon.xml"),
                Path("res/drawable/start.xml"),
            ],
        )
        self.assertEqual(
            sorted(path.relative_to(output).as_posix() for path in output.rglob("*.*")),
            ["mipmap-xxxhdpi-v4/icon_foreground.webp", "mipmap/icon.webp"],
        )

    def test_styles_of_value_resources(self) -> None:
        values = self.root / "values.xml"
        values.write_text(
            '<resources><style name="A" /><item type="style" name="B" />'
            '<item type="color" name="C">#fff</item></resources>'
        )
        self.assertEqual(shell_overrides.defined_styles([values]), {"A", "B"})

    def plist(self, name: str, data: dict) -> Path:
        path = self.root / name
        path.write_bytes(plistlib.dumps(data))
        return path

    def test_plist_keys_and_owned_keys(self) -> None:
        first = self.plist("first.plist", {"UIStatusBarHidden": True})
        second = self.plist("second.plist", {"UIStatusBarHidden": False, "Other": 1})
        keys = shell_overrides.plist_keys([first, second])
        self.assertEqual(keys, {"UIStatusBarHidden": first, "Other": second})
        shell_overrides.check_owned(keys, {"CFBundleIdentifier": "application_id"})
        owned = self.plist("owned.plist", {"CFBundleIdentifier": "org.example"})
        with self.assertRaisesRegex(
            ValueError,
            "owned.plist sets CFBundleIdentifier, which belongs to application_id",
        ):
            shell_overrides.check_owned(
                shell_overrides.plist_keys([owned]),
                {"CFBundleIdentifier": "application_id"},
            )

    def test_application_plist_keys_replace_shell_and_add_on_keys(self) -> None:
        shell = plistlib.dumps(
            {"UIStatusBarHidden": True, "UILaunchScreen": {}, "Kept": 1}
        ).decode()
        add_on = plistlib.dumps({"UIStatusBarHidden": True, "AddOn": 2}).decode()
        override = self.plist("app.plist", {"UIStatusBarHidden": False})
        text, fragments, keys = shell_overrides.yield_plist_keys(
            shell, [add_on], [override], {}
        )
        self.assertEqual(keys, {"UIStatusBarHidden"})
        self.assertEqual(plistlib.loads(text.encode()), {"UILaunchScreen": {}, "Kept": 1})
        self.assertEqual(plistlib.loads(fragments[0].encode()), {"AddOn": 2})
        # Without overrides, the files stay as they are.
        self.assertEqual(
            shell_overrides.yield_plist_keys(shell, [add_on], [], {}),
            (shell, [add_on], set()),
        )

    def test_plist_without_keys(self) -> None:
        text = plistlib.dumps({"A": 1, "B": 2}).decode()
        self.assertEqual(
            plistlib.loads(shell_overrides.without_plist_keys(text, ["B", "C"]).encode()),
            {"A": 1},
        )


if __name__ == "__main__":
    unittest.main()
