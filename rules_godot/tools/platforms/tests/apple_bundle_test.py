"""Read archived and directory iOS applications alike."""

import stat
import tempfile
import unittest
import zipfile
from pathlib import Path

from tools.platforms.apple_bundle import (
    application_bundle,
    bundle_files,
    bundle_identity,
)


class AppleBundleTest(unittest.TestCase):
    def test_directory_and_archive_read_as_the_same_members(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            app = base / "directory" / "game.app"
            (app / "Base.lproj").mkdir(parents=True)
            (app / "Info.plist").write_bytes(b"plist")
            (app / "Base.lproj" / "Launch.storyboardc").write_bytes(b"launch")
            ipa = base / "game.ipa"
            with zipfile.ZipFile(ipa, "w") as archive:
                archive.writestr("Payload/", b"")
                archive.writestr("Payload/game.app/Info.plist", b"plist")
                archive.writestr(
                    "Payload/game.app/Base.lproj/Launch.storyboardc", b"launch"
                )
            self.assertEqual(bundle_files(ipa), bundle_files(app))
            self.assertEqual(
                [
                    "Payload/game.app/Base.lproj/Launch.storyboardc",
                    "Payload/game.app/Info.plist",
                ],
                sorted(bundle_files(app)),
            )

    def test_only_selected_files_are_read(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            app = Path(temp) / "game.app"
            app.mkdir()
            (app / "Info.plist").write_bytes(b"plist")
            (app / "game").write_bytes(b"executable")
            self.assertEqual(
                {"Payload/game.app/Info.plist": b"plist"},
                bundle_files(app, lambda name: name.endswith(".plist")),
            )

    def test_directory_identity_follows_member_names_and_contents(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            identities = []
            for copy, content in [("a", b"one"), ("b", b"one"), ("c", b"two")]:
                app = Path(temp) / copy / "game.app"
                app.mkdir(parents=True)
                (app / "Info.plist").write_bytes(content)
                identities.append(bundle_identity(app))
            self.assertEqual(identities[0], identities[1])
            self.assertNotEqual(identities[0][0], identities[2][0])
            self.assertEqual(3, identities[0][1])

    def test_both_forms_become_a_real_bundle_in_work(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            # Runfiles present a directory bundle as symbolic links.
            (base / "outputs").mkdir()
            (base / "outputs" / "Info.plist").write_bytes(b"plist")
            app = base / "game.app"
            app.mkdir()
            (app / "Info.plist").symlink_to(base / "outputs" / "Info.plist")
            ipa = base / "game.ipa"
            with zipfile.ZipFile(ipa, "w") as archive:
                archive.writestr("Payload/game.app/Info.plist", b"plist")
            for source in [app, ipa]:
                with self.subTest(source=source.name):
                    work = base / ("work-" + source.suffix[1:])
                    bundle = application_bundle(source, work)
                    self.assertEqual(work / "Payload" / "game.app", bundle)
                    self.assertFalse((bundle / "Info.plist").is_symlink())
                    self.assertEqual(b"plist", (bundle / "Info.plist").read_bytes())

    def test_archive_members_must_stay_inside(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            ipa = base / "game.ipa"
            link = zipfile.ZipInfo("Payload/game.app/link")
            link.external_attr = (stat.S_IFLNK | 0o777) << 16
            for member in [zipfile.ZipInfo("../escape"), zipfile.ZipInfo("/abs"), link]:
                with zipfile.ZipFile(ipa, "w") as archive:
                    archive.writestr(member, b"")
                with (
                    self.subTest(member=member.filename),
                    self.assertRaisesRegex(
                        ValueError, "^Unsafe IPA archive member: " + member.filename
                    ),
                ):
                    application_bundle(ipa, base / "work")

    def test_an_archive_holds_one_application(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            ipa = base / "game.ipa"
            with zipfile.ZipFile(ipa, "w") as archive:
                archive.writestr("Payload/a.app/Info.plist", b"plist")
                archive.writestr("Payload/b.app/Info.plist", b"plist")
            with self.assertRaisesRegex(ValueError, "Expected one application bundle"):
                application_bundle(ipa, base / "work")


if __name__ == "__main__":
    unittest.main()
