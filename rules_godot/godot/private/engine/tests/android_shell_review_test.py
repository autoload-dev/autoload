"""
Check that the Godot sources the repository pins match the reviewed Android shell.

The Android shell runs Godot's template activity unchanged and writes the manifest,
themes and command line of Godot's Android export. Each pinned source must carry the
template activity the engine profile names, and the upstream files the shell mirrors
must have a digest recorded when they were reviewed for that minor. A pin of a new
minor, or one whose reviewed files changed, fails here until its differences are
reviewed as docs/internal/android-shell.md describes.
"""

import hashlib
import sys
import unittest

from godot.private.engine.tests import pinned_sources

# The reviewed files of each minor under Godot's platform/android, with the SHA-256
# digests of their reviewed versions. Pins whose files match share one review.
REVIEWED = {
    "4.7": {
        "export/export_plugin.cpp": {
            "b00c8a24eeedff494441a9220270458c5d49261be78ae57a3473445c03aa07f8",
        },
        "export/gradle_export_util.cpp": {
            "d32cc5f663c1fad6b9b56bf9a2c4ed22c53a869f86aa4279b2fe17bb11e6809e",
        },
        "java/app/build.gradle": {
            "ed953e0de4e3334ad6959e30178e9d312a2b6ec8eb664e477913040dbae7d232",
        },
        "java/app/config.gradle": {
            "b639cb6bcf22ed5280d24612c24cfc238ded1a95eb87e14c6bd11d6366b83313",
        },
        "java/app/res/values/themes.xml": {
            "fa7cccb16370f63b4f01c9516f8a4b120d8a4613f4627de9cb2e374a5ac299fd",
        },
        "java/app/src/main/AndroidManifest.xml": {
            "2a68ba08e3e047ffdb9ff433d02035fb99046ee5478c4e2e2b0ed25f1a833605",
        },
        "java/lib/src/main/java/org/godotengine/godot/GodotActivity.kt": {
            "09adf896eb65e19b9d3524c6f5770d043f69ffd7c48bc36139bf68742cd8805a",
        },
    },
    "4.8": {
        "export/export_plugin.cpp": {
            "8e655eb88cdd949ef965af266f2f8749695aa366b4897a094c09ab489f1d27cb",
        },
        "export/gradle_export_util.cpp": {
            "6df225be23c9c90ef8a7f3721dc7af476e9c8a96c4967bb1660a4944e86bf76c",
        },
        "java/app/build.gradle": {
            "5253f4c7cb141911787d05149fd02dd41f2360b70239d7fed8ceb00ef044defb",
        },
        "java/app/config.gradle": {
            "1abde11607cc25567dba66a204ea43f4e55e6d6c537b20984d96fceb13836787",
        },
        "java/app/dataLib/src/main/AndroidManifest.xml": {
            "b1fd29230b6546412b71aa788454b3b9af9402191bdb41adafe6883b4eaada09",
        },
        "java/app/dataLib/src/main/res/values/themes.xml": {
            "fa7cccb16370f63b4f01c9516f8a4b120d8a4613f4627de9cb2e374a5ac299fd",
        },
        "java/app/src/main/AndroidManifest.xml": {
            "09a33d0c9c3bca5049ff8bfd2504b52a264d96c6c764e1eb7904765447fc3174",
        },
        "java/lib/src/main/java/org/godotengine/godot/GodotActivity.kt": {
            "73eba0b570bc5d93ef6c00bb1be581fa485fe1a1cc17a922659e32259953487f",
        },
    },
}

SOURCES = sys.argv[1:]
PLATFORM = "platform/android/"


class AndroidShellReviewTest(unittest.TestCase):
    def test_pinned_sources_match_the_reviewed_android_shell(self) -> None:
        self.assertTrue(SOURCES)
        for location in SOURCES:
            source = pinned_sources.RUNFILES / location
            version = pinned_sources.version(source)
            minor = pinned_sources.minor(source)
            with self.subTest(version=version):
                self.assertIn(minor, REVIEWED, f"Godot {minor} has no reviewed files")
                reviewed = REVIEWED[minor]
                activity = pinned_sources.profile(minor)["android"]["template_activity"]
                files = pinned_sources.files(
                    source,
                    {PLATFORM + path for path in set(reviewed) | {activity["upstream"]}},
                )
                files = {
                    path.removeprefix(PLATFORM): data for path, data in files.items()
                }
                copy = (
                    pinned_sources.WORKSPACE / "godot/private/engine" / activity["path"]
                )
                self.assertEqual(
                    files[activity["upstream"]],
                    copy.read_bytes(),
                    f"{copy.name} differs from Godot {version}'s template activity",
                )
                changed = sorted(
                    path
                    for path, digests in reviewed.items()
                    if hashlib.sha256(files.get(path, b"")).hexdigest() not in digests
                )
                self.assertEqual(
                    changed, [], f"Godot {version} changed reviewed Android shell files"
                )


if __name__ == "__main__":
    unittest.main(argv=sys.argv[:1])
