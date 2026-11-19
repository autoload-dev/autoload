"""The inspection helper's own reader of archived and directory iOS applications."""

import stat
import tempfile
import unittest
import zipfile
from pathlib import Path

from godot.testing.private.apple_bundle import application_bundle


class AppleBundleTest(unittest.TestCase):
    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)

    def _ipa(self, *members: str | zipfile.ZipInfo) -> Path:
        ipa = self.root / "game.ipa"
        with zipfile.ZipFile(ipa, "w") as archive:
            for member in members:
                archive.writestr(member, b"content")
        return ipa

    def test_directory_and_archive_give_the_same_bundle(self) -> None:
        # Runfiles present a directory bundle as symbolic links.
        (self.root / "outputs").mkdir()
        (self.root / "outputs/Launch.storyboardc").write_bytes(b"content")
        app = self.root / "game.app"
        (app / "Base.lproj").mkdir(parents=True)
        (app / "Info.plist").write_bytes(b"content")
        (app / "Base.lproj/Launch.storyboardc").symlink_to(
            self.root / "outputs/Launch.storyboardc"
        )
        ipa = self._ipa(
            "Payload/game.app/Info.plist",
            "Payload/game.app/Base.lproj/Launch.storyboardc",
        )
        bundles = {}
        for source in (app, ipa):
            with self.subTest(source=source.name):
                work = self.root / ("work-" + source.suffix[1:])
                bundle = application_bundle(source, work)
                self.assertEqual(work / "Payload/game.app", bundle)
                files = sorted(path for path in bundle.rglob("*") if not path.is_dir())
                self.assertFalse(any(path.is_symlink() for path in files))
                bundles[source.suffix] = {
                    path.relative_to(bundle).as_posix(): path.read_bytes()
                    for path in files
                }
        self.assertEqual(bundles[".app"], bundles[".ipa"])
        self.assertEqual(
            ["Base.lproj/Launch.storyboardc", "Info.plist"], sorted(bundles[".app"])
        )

    def test_unsafe_archive_members_are_rejected(self) -> None:
        link = zipfile.ZipInfo("Payload/game.app/link")
        link.external_attr = (stat.S_IFLNK | 0o777) << 16
        members = ("/Payload/game.app/Info.plist", "Payload/../escape", link)
        for index, member in enumerate(members):
            name = member if isinstance(member, str) else member.filename
            with self.subTest(member=name):
                ipa = self._ipa("Payload/game.app/Info.plist", member)
                work = self.root / f"work-{index}"
                with self.assertRaises(ValueError) as raised:
                    application_bundle(ipa, work)
                self.assertEqual(
                    "Unsafe IPA archive member: " + name, str(raised.exception)
                )
                self.assertFalse(work.exists())

    def test_archive_needs_exactly_one_application(self) -> None:
        cases = {
            "none": ("Payload/readme.txt",),
            "two": ("Payload/one.app/Info.plist", "Payload/two.app/Info.plist"),
        }
        for case, members in cases.items():
            with (
                self.subTest(case),
                tempfile.TemporaryDirectory() as work,
                self.assertRaisesRegex(
                    ValueError, "^Expected one application bundle, found "
                ),
            ):
                application_bundle(self._ipa(*members), Path(work))


if __name__ == "__main__":
    unittest.main()
