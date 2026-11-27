"""Engine AARs with source-built engine libraries and Android extension library ZIPs."""

import tempfile
import unittest
import zipfile
from pathlib import Path

from tools.platforms import package_android


class PackageAndroidTest(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)

    def test_engine_aar_replaces_the_engine_library_of_the_shell_library(self) -> None:
        original = self.root / "original.aar"
        with zipfile.ZipFile(original, "w") as archive:
            archive.writestr("classes.jar", b"original-java-shell")
            archive.writestr("AndroidManifest.xml", b"original-manifest")
            archive.writestr("jni/arm64-v8a/libgodot_android.so", b"original-engine")
            archive.writestr("jni/x86_64/libgodot_android.so", b"unused-cpu")
        engine_library = self.root / "libgodot_source.so"
        engine_library.write_bytes(b"source-built-engine")
        output = self.root / "engine.aar"
        package_android.package(
            output,
            [
                {
                    "source": str(engine_library),
                    "abi": "arm64-v8a",
                    "name": "libgodot_android.so",
                }
            ],
            original,
        )
        with zipfile.ZipFile(output) as archive:
            self.assertEqual(archive.read("classes.jar"), b"original-java-shell")
            self.assertEqual(
                archive.read("jni/arm64-v8a/libgodot_android.so"),
                b"source-built-engine",
            )
            self.assertNotIn("jni/x86_64/libgodot_android.so", archive.namelist())

    def test_engine_aar_drops_signatures_and_rejects_unsafe_entries(self) -> None:
        original = self.root / "original.aar"
        with zipfile.ZipFile(original, "w") as archive:
            archive.writestr("META-INF/CERT.RSA", b"signature")
            archive.writestr("META-INF/CERT.sf", b"signature")
            archive.writestr("META-INF/MANIFEST.MF", b"manifest")
            archive.writestr("jni/libgodot_android.so", b"not an ABI's")
            archive.writestr("assets/", b"")
        output = self.root / "engine.aar"
        package_android.package(output, [], original)
        with zipfile.ZipFile(output) as archive:
            self.assertEqual(
                sorted(archive.namelist()),
                ["META-INF/MANIFEST.MF", "jni/libgodot_android.so"],
            )
        with zipfile.ZipFile(original, "w") as archive:
            archive.writestr("../escape", b"")
        with self.assertRaisesRegex(ValueError, "^unsafe AAR entry: ../escape$"):
            package_android.package(output, [], original)

    def test_engine_aar_manifest_names_the_source_built_engine(self) -> None:
        manifest = (
            '<manifest xmlns:android="http://schemas.android.com/apk/res/android">\n'
            "  <application>\n"
            "    <meta-data\n"
            '        android:name="org.godotengine.library.version"\n'
            '        android:value="4.7.2.stable" />\n'
            "  </application>\n"
            "</manifest>\n"
        )
        original = self.root / "original.aar"
        with zipfile.ZipFile(original, "w") as archive:
            archive.writestr("AndroidManifest.xml", manifest)
        output = self.root / "engine.aar"

        def library(abi: str, origin: str) -> dict[str, str]:
            files = {"build": f"custom-{origin}", "hash": "abc1234"}
            for key, value in files.items():
                (self.root / f"{abi}.{key}").write_text(value)
            engine_library = self.root / f"{abi}.so"
            engine_library.write_bytes(b"source-built-engine")
            return {
                "source": str(engine_library),
                "abi": abi,
                "name": "libgodot_android.so",
                "version": "4.7.2.stable",
            } | {key: str(self.root / f"{abi}.{key}") for key in files}

        arm64 = library("arm64-v8a", "git")
        package_android.package(output, [arm64, library("x86_64", "git")], original)
        with zipfile.ZipFile(output) as archive:
            self.assertEqual(
                archive.read("AndroidManifest.xml").decode(),
                manifest.replace('"4.7.2.stable"', '"4.7.2.stable.custom-git.abc1234"'),
            )
        with self.assertRaisesRegex(ValueError, "different versions: .*bazel.*git"):
            package_android.package(output, [arm64, library("x86_64", "bazel")], original)
        with zipfile.ZipFile(original, "w") as archive:
            archive.writestr("AndroidManifest.xml", "<manifest />")
        with self.assertRaisesRegex(ValueError, "org.godotengine.library.version once"):
            package_android.package(output, [arm64], original)

    def test_android_extension_zip_uses_package_manager_library_names(self) -> None:
        library = self.root / "libextension.so"
        library.write_bytes(b"extension")
        output = self.root / "jni.zip"
        package_android.package(output, [{"source": str(library), "abi": "arm64-v8a"}])
        with zipfile.ZipFile(output) as archive:
            self.assertEqual(archive.read("lib/arm64-v8a/libextension.so"), b"extension")
        for name in ["extension.so", "libextension", "lib/extension.so", "lib\\a.so"]:
            with (
                self.subTest(name=name),
                self.assertRaisesRegex(ValueError, "lib\\*\\.so"),
            ):
                package_android.package(
                    output, [{"source": str(library), "abi": "arm64-v8a", "name": name}]
                )
        with self.assertRaisesRegex(ValueError, "^unsupported Android ABI: mips$"):
            package_android.package(output, [{"source": str(library), "abi": "mips"}])
        with self.assertRaisesRegex(
            ValueError, "^duplicate Android library: lib/arm64-v8a/libextension.so$"
        ):
            package_android.package(
                output, [{"source": str(library), "abi": "arm64-v8a"}] * 2
            )


if __name__ == "__main__":
    unittest.main()
