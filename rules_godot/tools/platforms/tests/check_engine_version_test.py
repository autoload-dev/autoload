"""The engine versions check_engine_version reads from engine artifacts and checks."""

import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

from tools.platforms import check_engine_version

LIBRARY = """<?xml version="1.0" encoding="utf-8"?>
<manifest xmlns:android="http://schemas.android.com/apk/res/android"
    package="org.example.plugin">
  <uses-permission android:name="android.permission.CAMERA" />
  <meta-data android:name="org.godotengine.library.version" android:value="4.7.2.stable" />
  <application />
</manifest>
"""


class CheckEngineVersionTest(unittest.TestCase):
    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)

    def check_engine(self, *engine: str) -> None:
        output = self.root / "engine_version"
        argv = ["check", "--output", str(output), *engine]
        with mock.patch("sys.argv", argv):
            check_engine_version.main()

    def test_engine_versions_are_read_but_not_compared_with_the_pack(self) -> None:
        manifest = self.root / "AndroidManifest.xml"
        manifest.write_text(LIBRARY)
        library = self.root / "libgodot.a"
        library.write_bytes(b"\0header Godot Engine v4.8.beta1.official - https\0")
        self.assertEqual(
            check_engine_version.manifest_versions(manifest), {"4.7.2.stable"}
        )
        self.assertEqual(
            check_engine_version.library_versions(library), {"4.8.beta1.official"}
        )
        # An engine older than the pack's editor is accepted; no pack version exists here.
        self.check_engine("--android-manifest", str(manifest))
        self.check_engine("--library", str(library))

    def test_the_projects_rendering_method_must_be_one_its_engine_runs(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            facts = Path(directory) / "facts.json"
            method = "rendering/renderer/rendering_method"
            facts.write_text(json.dumps({"settings": {method: "gl_compatibility"}}))
            check_engine_version.require_rendering_method(facts, ["gl_compatibility"])
            with self.assertRaisesRegex(
                SystemExit,
                "renders with gl_compatibility, but its engine runs only mobile",
            ):
                check_engine_version.require_rendering_method(facts, ["mobile"])
            # Godot's default is forward_plus when the project sets none.
            facts.write_text('{"settings": {}}')
            with self.assertRaisesRegex(SystemExit, "renders with forward_plus"):
                check_engine_version.require_rendering_method(facts, ["gl_compatibility"])

    def test_opaque_engine_version_assertion_is_checked(self) -> None:
        library = self.root / "libgodot.a"
        library.write_bytes(b"Godot Engine v4.7.2.stable.official\0")
        with self.assertRaisesRegex(SystemExit, "engine_version assertion"):
            self.check_engine(
                "--library", str(library), "--assert-version", "4.8.0-beta1"
            )
        self.check_engine("--library", str(library), "--assert-version", "4.7.2")

    def test_engine_aar_ships_the_engine_library_of_the_platform_slice_abi(self) -> None:
        native_libs = self.root / "native_libs.zip"
        with zipfile.ZipFile(native_libs, "w") as archive:
            archive.writestr("lib/arm64-v8a/libgodot_android.so", b"engine")
        engine = ["--android-native-libs", str(native_libs)]
        self.check_engine(*engine, "--android-abi", "arm64-v8a")
        with self.assertRaisesRegex(SystemExit, "no libgodot_android.so for x86_64"):
            self.check_engine(*engine, "--android-abi", "x86_64")

    def test_engine_aar_manifests_name_the_engine_they_ship(self) -> None:
        digest = "0123456789abcdef0123456789abcdef01234567"
        parse = check_engine_version.parse
        self.assertEqual(
            parse(f"4.7.2.stable.custom-git.{digest}"),
            check_engine_version.Version((4, 7, 2), "stable", "custom-git", digest),
        )
        self.assertEqual(
            parse("4.8.beta1.official"),
            check_engine_version.Version((4, 8, 0), "beta1", "official"),
        )
        self.assertEqual(
            parse("4.8.0.beta"), check_engine_version.Version((4, 8, 0), "beta")
        )
        # A stamped build may name a short commit.
        self.assertEqual(parse("4.7.2.stable.custom-git.abc1234").digest, "abc1234")

        def aar(version: str, library: bytes) -> list[str]:
            manifest = self.root / f"{version}.xml"
            manifest.write_text(LIBRARY.replace("4.7.2.stable", version))
            native_libs = self.root / f"{version}.zip"
            with zipfile.ZipFile(native_libs, "w") as archive:
                archive.writestr(
                    "lib/arm64-v8a/libother.so", b"Godot Engine v3.0.stable\0"
                )
                archive.writestr("lib/arm64-v8a/libgodot_android.so", library)
            return [
                "--android-manifest",
                str(manifest),
                "--android-native-libs",
                str(native_libs),
            ]

        custom = b"\0Godot Engine v4.7.2.stable.custom-git\0" + digest.encode() + b"\0"
        self.check_engine(*aar(f"4.7.2.stable.custom-git.{digest}", custom))
        # A prebuilt engine's manifest names no build or hash; a prerelease no number.
        self.check_engine(*aar("4.7.2.stable", custom))
        self.check_engine(*aar("4.8.0.beta", b"Godot Engine v4.8.beta1.official\0"))
        # A library that names no version passes, as before.
        self.check_engine(*aar("4.7.2.stable", b"engine"))
        for version, library, error in [
            (
                "4.7.2.stable",
                b"Godot Engine v4.8.beta1.official\0",
                "library is Godot 4.8",
            ),
            (
                f"4.7.2.stable.custom-git.{digest}",
                custom.replace(b"custom-git", b"custom-bazel"),
                "is Godot",
            ),
            (f"4.7.2.stable.custom-git.{'f' * 40}", custom, "no hash ffff"),
        ]:
            with (
                self.subTest(version=version),
                self.assertRaisesRegex(SystemExit, "manifest names Godot .*" + error),
            ):
                self.check_engine(*aar(version, library))


if __name__ == "__main__":
    unittest.main()
