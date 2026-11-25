"""
The Android inspector's checks of a bundle's manifest, universal APK and symbols.

Sections: Class definitions, Bundle inspection.
"""

import contextlib
import hashlib
import io
import json
import os
import struct
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

from godot.private.testing import inspect_android_bundle
from godot.private.testing.inspect_android_bundle import apk_classes, defined_classes

# ==== Class definitions =======================================================


def dex_types(defined: str, referenced: str) -> bytes:
    """A DEX class table defining one type and referring to another."""
    strings = [f"L{name.replace('.', '/')};".encode() for name in [defined, referenced]]
    dex = bytearray(160)
    dex[:8] = b"dex\n035\0"
    struct.pack_into("<II", dex, 36, 112, 0x12345678)
    struct.pack_into("<II", dex, 56, 2, 112)
    struct.pack_into("<II", dex, 64, 2, 120)
    struct.pack_into("<II", dex, 96, 1, 128)
    struct.pack_into("<II", dex, 120, 0, 1)
    for index, value in enumerate(strings):
        struct.pack_into("<I", dex, 112 + index * 4, len(dex))
        dex.extend(bytes([len(value)]) + value + b"\0")
    struct.pack_into("<I", dex, 32, len(dex))
    return bytes(dex)


class ClassDefinitionsTest(unittest.TestCase):
    def test_reference_does_not_supply_missing_runtime_class(self) -> None:
        data = dex_types(
            "androidx.concurrent.futures.AbstractResolvableFuture",
            "com.google.common.util.concurrent.ListenableFuture",
        )
        self.assertEqual(
            {"androidx.concurrent.futures.AbstractResolvableFuture"},
            defined_classes(data),
        )

    def test_multidex_can_supply_a_definition_referenced_in_another_file(self) -> None:
        first = dex_types("example.Counter", "example.Future")
        second = dex_types("example.Future", "example.Counter")
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w") as archive:
            archive.writestr("classes.dex", first)
            archive.writestr("classes2.dex", second)
            archive.writestr("assets/references.txt", b"Lexample/NotDefined;")
        with zipfile.ZipFile(stream) as archive:
            self.assertEqual({"example.Counter", "example.Future"}, apk_classes(archive))

    def test_invalid_or_truncated_headers_and_tables_are_rejected(self) -> None:
        data = dex_types("example.Counter", "example.Future")
        bad_header = bytearray(data)
        struct.pack_into("<I", bad_header, 36, 108)
        bad_table = bytearray(data)
        struct.pack_into("<I", bad_table, 100, len(data) + 4)
        for invalid in [
            b"not dex",
            data[:100],
            data[:-5],
            bytes(bad_header),
            bytes(bad_table),
        ]:
            with self.subTest(size=len(invalid)), self.assertRaises(ValueError):
                defined_classes(invalid)


# ==== Bundle inspection =======================================================


def pck(files: dict[str, bytes]) -> bytes:
    """An unencrypted standalone Godot 4.7.2 PCK v4 of the files."""
    # Header: magic, format version, Godot version, flags, file base, directory.
    file_base = 40
    data = b"".join(files.values())
    pack = struct.pack(
        "<6IQQ", 0x43504447, 4, 4, 7, 2, 0, file_base, file_base + len(data)
    )
    directory = struct.pack("<I", len(files))
    offset = 0
    for path, content in files.items():
        name = path.encode() + bytes(-len(path) % 4 or 4)
        directory += struct.pack("<I", len(name)) + name
        directory += struct.pack("<QQ", offset, len(content))
        directory += hashlib.md5(content).digest() + struct.pack("<I", 0)
        offset += len(content)
    return pack + data + directory


def elf_library(build_id: bytes, *sections: str) -> bytes:
    """A 64-bit ELF library with a GNU build ID note and further named sections."""
    note = struct.pack("<III", 4, len(build_id), 3) + b"GNU\0" + build_id
    names = [".note.gnu.build-id", *sections, ".shstrtab"]
    table = b"\0" + b"".join(name.encode() + b"\0" for name in names)
    # Section type, contents: a note, program data and the section name table.
    contents = [(7, note), *[(1, b"section") for _ in sections], (3, table)]
    # Fields: name, type, flags, address, offset, size, link, info, alignment, entry size.
    body, headers = b"", bytes(64)
    for name, (kind, data) in zip(names, contents, strict=True):
        headers += struct.pack(
            "<IIQQQQIIQQ",
            table.index(name.encode() + b"\0"),
            kind,
            0,
            0,
            64 + len(body),
            len(data),
            0,
            0,
            1,
            0,
        )
        body += data
    # Fields: type, machine, version, entry, program and section header offsets,
    # flags, header size, program header size and count, section header size and
    # count, index of the name table.
    header = b"\x7fELF" + bytes([2, 1, 1]) + bytes(9)
    header += struct.pack(
        "<HHIQQQIHHHHHH",
        3,
        183,
        1,
        0,
        0,
        64 + len(body),
        0,
        64,
        0,
        0,
        64,
        len(names) + 1,
        len(names),
    )
    return header + body + headers


_APPLICATION_ID = "com.example.game"
_MANIFEST = (
    '<manifest package="com.example.game">'
    '<uses-sdk android:minSdkVersion="24"/>'
    '<activity android:name="com.godot.game.GodotApp"/>'
    "</manifest>"
)
_LIBRARY = "arm64-v8a/libgame.so"
_BUILD_ID = bytes.fromhex("7eb76e5a")


class BundleInspectionTest(unittest.TestCase):
    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.outputs = self.root / "outputs"
        self.outputs.mkdir()
        self.manifest = _MANIFEST
        # The universal APK bundletool generates, by member and whether it is stored.
        self.apk: dict[str, tuple[bytes, bool]] = {
            "assets/main.pck": (pck({"main/main.gd": b"extends Node"}), True),
            "assets/_cl_": (b"command line", False),
            "lib/" + _LIBRARY: (elf_library(_BUILD_ID), False),
            "classes.dex": (
                dex_types("com.godot.game.GodotApp", "example.Future"),
                False,
            ),
        }
        self.subcommands: list[str] = []

    def _bundletool(self, command: list[str | Path], _home: Path) -> str:
        """Answer validate, dump manifest and build-apks as bundletool does."""
        self.assertEqual(
            ["java", "-jar", "bundletool.jar"], [str(c) for c in command[:3]]
        )
        subcommand = str(command[3])
        self.subcommands.append(subcommand)
        if subcommand == "dump":
            return self.manifest
        if subcommand == "build-apks":
            self.assertIn("--mode=universal", command)
            [output] = [str(c) for c in command if str(c).startswith("--output=")]
            apk = io.BytesIO()
            with zipfile.ZipFile(apk, "w") as archive:
                for name, (data, stored) in self.apk.items():
                    kind = zipfile.ZIP_STORED if stored else zipfile.ZIP_DEFLATED
                    archive.writestr(name, data, compress_type=kind)
            with zipfile.ZipFile(output.removeprefix("--output="), "w") as apks:
                apks.writestr("universal.apk", apk.getvalue())
        return ""

    def _symbols(self, libraries: dict[str, bytes]) -> str:
        """A debug symbol ZIP of <abi>/<name>.so entries."""
        path = self.root / "symbols.zip"
        with zipfile.ZipFile(path, "w") as archive:
            for name, data in libraries.items():
                archive.writestr(name, data)
        return str(path)

    def _inspect(self, *options: str) -> str:
        """Run the inspector's command line; return what it prints."""
        argv = [
            "inspect_android_bundle",
            "--bundle",
            str(self.root / "game.aab"),
            "--bundletool",
            "bundletool.jar",
            "--java",
            "java",
            "--application-id",
            _APPLICATION_ID,
            *options,
        ]
        stdout = io.StringIO()
        with (
            mock.patch.object(sys, "argv", argv),
            mock.patch.object(
                inspect_android_bundle, "run", side_effect=self._bundletool
            ),
            mock.patch.dict(
                os.environ, {"TEST_UNDECLARED_OUTPUTS_DIR": str(self.outputs)}
            ),
            contextlib.redirect_stdout(stdout),
        ):
            inspect_android_bundle.main()
        return stdout.getvalue()

    def assertRejects(self, message: str, *options: str) -> None:
        evidence = self.outputs / "bundle.json"
        evidence.unlink(missing_ok=True)
        with self.assertRaises(ValueError) as raised:
            self._inspect(*options)
        self.assertEqual(message, str(raised.exception))
        self.assertFalse(evidence.exists())

    def test_base_manifest_must_name_the_application_and_activity(self) -> None:
        self._inspect()
        self.assertEqual(["validate", "dump", "build-apks"], self.subcommands)
        for manifest in (
            _MANIFEST.replace(_APPLICATION_ID, "com.example.other"),
            _MANIFEST.replace("com.godot.game.GodotApp", "com.example.Activity"),
        ):
            with self.subTest(manifest=manifest):
                self.manifest = manifest
                self.assertRejects(f"Unexpected base manifest:\n{manifest}")

    def test_manifest_entries_must_appear_in_the_base_manifest(self) -> None:
        self._inspect("--manifest-entry", 'android:minSdkVersion="24"')
        self.assertRejects(
            f"Manifest lacks ['android:maxSdkVersion=\"35\"']:\n{_MANIFEST}",
            "--manifest-entry",
            'android:minSdkVersion="24"',
            "--manifest-entry",
            'android:maxSdkVersion="35"',
        )

    def test_pack_must_be_stored_uncompressed(self) -> None:
        self.apk["assets/main.pck"] = (self.apk["assets/main.pck"][0], False)
        self.assertRejects("assets/main.pck must be stored uncompressed")

    def test_command_line_file_must_be_packaged(self) -> None:
        del self.apk["assets/_cl_"]
        self.assertRejects("assets/_cl_, the export's command line, is missing")

    def test_required_native_libraries_must_be_packaged(self) -> None:
        self._inspect("--library", "lib/" + _LIBRARY)
        self.assertRejects(
            "Missing native libraries: lib/x86_64/libgame.so, lib/x86_64/libgodot.so",
            "--library",
            "lib/x86_64/libgodot.so",
            "--library",
            "lib/" + _LIBRARY,
            "--library",
            "lib/x86_64/libgame.so",
        )

    def test_required_java_classes_must_be_defined(self) -> None:
        self._inspect("--java-class", "com.godot.game.GodotApp")
        # A class the DEX only refers to is not packaged.
        self.assertRejects(
            "Missing Java classes: example.Future",
            "--java-class",
            "com.godot.game.GodotApp",
            "--java-class",
            "example.Future",
        )

    def test_pack_must_contain_required_resources(self) -> None:
        self._inspect("--pck-file", "main/main.gd")
        self.assertRejects(
            "PCK lacks resources: ['main/other.gd']",
            "--pck-file",
            "main/main.gd",
            "--pck-file",
            "main/other.gd",
        )

    def test_debug_symbols_match_the_packaged_libraries(self) -> None:
        symbols = self._symbols(
            {_LIBRARY: elf_library(_BUILD_ID, ".symtab", ".debug_info")}
        )
        printed = self._inspect(
            "--debug-symbols",
            symbols,
            "--symbol-library",
            _LIBRARY,
            "--debug-info",
        )
        self.assertEqual(
            {
                "application_id": _APPLICATION_ID,
                "pck": {
                    "format_version": 4,
                    "godot_version": "4.7.2",
                    "file_count": 1,
                    "paths": ["main/main.gd"],
                },
                "native_libraries": ["lib/" + _LIBRARY],
                "debug_symbols": [_LIBRARY],
            },
            json.loads((self.outputs / "bundle.json").read_text()),
        )
        self.assertEqual(
            f'rules_godot: Android App Bundle verified: ["lib/{_LIBRARY}"]\n', printed
        )

    def test_mismatched_debug_symbols_are_rejected(self) -> None:
        unstripped = elf_library(_BUILD_ID, ".symtab", ".debug_info")
        other = bytes.fromhex("0badc0de")
        cases = {
            "Debug symbols lack: arm64-v8a/libother.so": (
                {_LIBRARY: unstripped},
                ["--symbol-library", "arm64-v8a/libother.so"],
            ),
            "Debug symbols for x86_64/libgame.so, which the APK lacks": (
                {_LIBRARY: unstripped, "x86_64/libgame.so": unstripped},
                [],
            ),
            f"{_LIBRARY}: the build IDs of package and symbols differ": (
                {_LIBRARY: elf_library(other, ".symtab", ".debug_info")},
                [],
            ),
            f"{_LIBRARY}: the debug symbols are stripped": (
                {_LIBRARY: elf_library(_BUILD_ID, ".debug_info")},
                [],
            ),
            f"{_LIBRARY}: the debug symbols have no DWARF": (
                {_LIBRARY: elf_library(_BUILD_ID, ".symtab")},
                ["--debug-info"],
            ),
        }
        for message, (libraries, options) in cases.items():
            with self.subTest(message):
                self.assertRejects(
                    message, "--debug-symbols", self._symbols(libraries), *options
                )
        with self.subTest("unstripped package"):
            self.apk["lib/" + _LIBRARY] = (unstripped, False)
            self.assertRejects(
                f"{_LIBRARY}: the APK packages it unstripped",
                "--debug-symbols",
                self._symbols({_LIBRARY: unstripped}),
            )

    def test_failing_tool_reports_its_output(self) -> None:
        home = self.root / "home"
        printed = inspect_android_bundle.run(
            [sys.executable, "-c", "import os; print(os.environ['HOME'])"], home
        )
        self.assertEqual(f"{home}\n", printed)
        failing: list[str | Path] = [
            sys.executable,
            "-c",
            "print('bad bundle'); raise SystemExit(3)",
        ]
        with self.assertRaises(RuntimeError) as raised:
            inspect_android_bundle.run(failing, home)
        self.assertEqual(f"{sys.executable} failed:\nbad bundle\n", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
