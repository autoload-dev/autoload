"""
Inspect the App Bundle of an application built with the source-built Android engine.

bundletool validates the bundle and generates its universal APK, as Google Play derives
the installed APKs from an uploaded bundle. The APK must package the source-built engine
and the C ABI extension, define Godot's Java shell, and match the application's debug
symbols by build ID. No device runs it.
"""

import os
import struct
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

from tools.platforms.native_symbols import elf_build_id, elf_sections

APPLICATION_ID = "org.example.rulesgodot.source"
ACTIVITY = "com.godot.game.GodotApp"
LIBRARIES = ["arm64-v8a/libgodot_android.so", "arm64-v8a/libhello_native.so"]
# The repacked shell library's dex and the source-built engine's unstripped symbols both
# pass the runtime bridge; rules_android fails the build on a duplicate provider or class.
SHELL_CLASS = "org.godotengine.godot.Godot"


def runfile(path: str) -> Path:
    return Path(os.environ["TEST_SRCDIR"], path)


def defined_classes(dex: bytes) -> set[str]:
    """Read defined class names from a standard little-endian DEX class_defs table."""
    # https://source.android.com/docs/core/runtime/dex-format#header-item
    if len(dex) < 112 or dex[:4] != b"dex\n" or dex[7] != 0:
        raise ValueError("Invalid DEX header")
    size, header_size, endian = struct.unpack_from("<III", dex, 32)
    if size != len(dex) or header_size != 112 or endian != 0x12345678:
        raise ValueError("Invalid DEX size, header or byte order")
    string_count, strings = struct.unpack_from("<II", dex, 56)
    type_count, types = struct.unpack_from("<II", dex, 64)
    class_count, classes = struct.unpack_from("<II", dex, 96)
    result = set()
    for index in range(class_count):
        type_index = struct.unpack_from("<I", dex, classes + index * 32)[0]
        if type_index >= type_count:
            raise ValueError("DEX class type outside type table")
        string_index = struct.unpack_from("<I", dex, types + type_index * 4)[0]
        if string_index >= string_count:
            raise ValueError("DEX descriptor outside string table")
        offset = struct.unpack_from("<I", dex, strings + string_index * 4)[0]
        # Skip the ULEB128 UTF-16 length that precedes the MUTF-8 descriptor.
        while dex[offset] & 0x80:
            offset += 1
        offset += 1
        descriptor = dex[offset : dex.index(b"\0", offset)].decode("utf-8")
        result.add(descriptor[1:-1].replace("/", "."))
    return result


class AndroidSourceBundleTest(unittest.TestCase):
    def setUp(self) -> None:
        bundle, symbols, bundletool, *java = sys.argv[1:]
        self.bundle = runfile(bundle)
        self.symbols = runfile(symbols)
        javas = [path for path in java if path.endswith("/bin/java")]
        self.assertEqual(len(javas), 1, java)
        self.bundletool = [str(runfile(javas[0])), "-jar", str(runfile(bundletool))]
        self.work = Path(tempfile.mkdtemp(dir=os.environ.get("TEST_TMPDIR")))

    def run_bundletool(self, *arguments: str) -> str:
        result = subprocess.run(
            [*self.bundletool, *arguments],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            env={**os.environ, "HOME": str(self.work)},
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout)
        return result.stdout

    def test_source_built_bundle_packages_engine_shell_and_symbols(self) -> None:
        self.run_bundletool("validate", f"--bundle={self.bundle}")
        manifest = self.run_bundletool("dump", "manifest", f"--bundle={self.bundle}")
        self.assertIn(f'package="{APPLICATION_ID}"', manifest)
        self.assertIn(ACTIVITY, manifest)
        apks = self.work / "universal.apks"
        self.run_bundletool(
            "build-apks",
            f"--bundle={self.bundle}",
            f"--output={apks}",
            "--mode=universal",
        )
        with zipfile.ZipFile(apks) as archive:
            archive.extract("universal.apk", self.work)
        with zipfile.ZipFile(self.work / "universal.apk") as apk:
            self.assertEqual(
                apk.getinfo("assets/main.pck").compress_type, zipfile.ZIP_STORED
            )
            names = set(apk.namelist())
            self.assertIn("assets/_cl_", names)
            for library in LIBRARIES:
                self.assertIn("lib/" + library, names)
            classes = set()
            for name in names:
                if name.startswith("classes") and name.endswith(".dex"):
                    classes |= defined_classes(apk.read(name))
            self.assertIn(SHELL_CLASS, classes)
            with zipfile.ZipFile(self.symbols) as archive:
                self.assertLessEqual(set(LIBRARIES), set(archive.namelist()))
                for name in archive.namelist():
                    with self.subTest(library=name):
                        symbols = elf_sections(archive.read(name))
                        packaged = elf_sections(apk.read("lib/" + name))
                        self.assertTrue(elf_build_id(symbols))
                        self.assertEqual(elf_build_id(symbols), elf_build_id(packaged))
                        self.assertIn(".symtab", symbols)
                        self.assertFalse({".symtab", ".debug_info"} & set(packaged))


if __name__ == "__main__":
    unittest.main(argv=sys.argv[:1])
