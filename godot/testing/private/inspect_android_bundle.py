"""
Inspect an Android App Bundle through the APKs bundletool generates from it.

Google Play installs APKs that bundletool derives from an uploaded bundle. This
check validates the bundle, generates its universal APK and inspects the
manifest, the uncompressed PCK, the command line file, the native libraries and
the Java classes in it, and matches the application's debug symbols with the
libraries it packages. No device runs the APK.
"""

import argparse
import json
import os
import struct
import subprocess
import tempfile
import zipfile
from pathlib import Path

from godot.testing.private.native_symbols import elf_build_id, elf_sections
from godot.testing.private.pck import pck_contents

_ACTIVITY = "com.godot.game.GodotApp"


def defined_classes(dex: bytes) -> set[str]:
    """Read defined class names from standard little-endian DEX class_defs tables."""
    # https://source.android.com/docs/core/runtime/dex-format#header-item
    if len(dex) < 112 or dex[:4] != b"dex\n" or dex[7] != 0:
        raise ValueError("Invalid DEX header")
    version = dex[4:7]
    if not version.isdigit() or not 35 <= int(version) <= 40:
        raise ValueError("Unsupported DEX version")
    size, header_size, endian = struct.unpack_from("<III", dex, 32)
    if size != len(dex) or header_size != 112 or endian != 0x12345678:
        raise ValueError("Invalid DEX size, header or byte order")

    def table(field: int, width: int) -> tuple[int, int]:
        count, offset = struct.unpack_from("<II", dex, field)
        if count and (offset < header_size or offset + count * width > size):
            raise ValueError("DEX table outside file")
        return count, offset

    string_count, strings = table(56, 4)
    type_count, types = table(64, 4)
    class_count, classes = table(96, 32)
    result = set()
    for index in range(class_count):
        type_index = struct.unpack_from("<I", dex, classes + index * 32)[0]
        if type_index >= type_count:
            raise ValueError("DEX class type outside type table")
        string_index = struct.unpack_from("<I", dex, types + type_index * 4)[0]
        if string_index >= string_count:
            raise ValueError("DEX descriptor outside string table")
        offset = struct.unpack_from("<I", dex, strings + string_index * 4)[0]
        for _ in range(5):
            if offset >= size:
                raise ValueError("DEX string outside file")
            byte = dex[offset]
            offset += 1
            if not byte & 0x80:
                break
        else:
            raise ValueError("Invalid DEX string length")
        end = dex.find(b"\0", offset)
        if end < 0:
            raise ValueError("Unterminated DEX descriptor")
        descriptor = dex[offset:end].decode("utf-8")
        if not descriptor.startswith("L") or not descriptor.endswith(";"):
            raise ValueError("Invalid DEX class descriptor")
        result.add(descriptor[1:-1].replace("/", "."))
    return result


def apk_classes(apk: zipfile.ZipFile) -> set[str]:
    """Collect actual class definitions across all of an APK's DEX files."""
    definitions = set()
    for name in apk.namelist():
        if name.startswith("classes") and name.endswith(".dex"):
            definitions.update(defined_classes(apk.read(name)))
    return definitions


def run(command: list[str | Path], home: Path) -> str:
    """Run a tool with an isolated HOME; return its combined output."""
    result = subprocess.run(
        [str(part) for part in command],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        env={**os.environ, "HOME": str(home)},
        check=False,
    )
    if result.returncode:
        raise RuntimeError(f"{command[0]} failed:\n{result.stdout}")
    return result.stdout


def check_symbols(apk: zipfile.ZipFile, args: argparse.Namespace) -> list[str]:
    """Match each library of the symbol ZIP with the one the APK packages."""
    with zipfile.ZipFile(args.debug_symbols) as archive:
        names = sorted(archive.namelist())
        missing = sorted(set(args.symbol_library) - set(names))
        if missing:
            raise ValueError("Debug symbols lack: " + ", ".join(missing))
        for name in names:
            try:
                packaged = apk.read("lib/" + name)
            except KeyError:
                raise ValueError(
                    f"Debug symbols for {name}, which the APK lacks"
                ) from None
            unstripped = archive.read(name)
            symbols = elf_sections(unstripped)
            sections = elf_sections(packaged)
            build_id = elf_build_id(symbols)
            if not build_id or build_id != elf_build_id(sections):
                raise ValueError(f"{name}: the build IDs of package and symbols differ")
            if ".symtab" not in symbols:
                raise ValueError(f"{name}: the debug symbols are stripped")
            if args.debug_info and ".debug_info" not in symbols:
                raise ValueError(f"{name}: the debug symbols have no DWARF")
            if {".symtab", ".debug_info"} & set(sections):
                raise ValueError(f"{name}: the APK packages it unstripped")
    return names


def inspect(args: argparse.Namespace, work: Path) -> dict:
    """Return the evidence for one bundle; raise on any unexpected content."""
    bundletool = [args.java, "-jar", args.bundletool]
    run([*bundletool, "validate", f"--bundle={args.bundle}"], work)
    manifest = run([*bundletool, "dump", "manifest", f"--bundle={args.bundle}"], work)
    if f'package="{args.application_id}"' not in manifest or _ACTIVITY not in manifest:
        raise ValueError(f"Unexpected base manifest:\n{manifest}")
    absent = [entry for entry in args.manifest_entry if entry not in manifest]
    if absent:
        raise ValueError(f"Manifest lacks {absent}:\n{manifest}")
    apks = work / "universal.apks"
    run(
        [
            *bundletool,
            "build-apks",
            f"--bundle={args.bundle}",
            f"--output={apks}",
            "--mode=universal",
        ],
        work,
    )
    with zipfile.ZipFile(apks) as archive:
        archive.extract("universal.apk", work)
    with zipfile.ZipFile(work / "universal.apk") as apk:
        pck = apk.getinfo("assets/main.pck")
        if pck.compress_type != zipfile.ZIP_STORED:
            raise ValueError("assets/main.pck must be stored uncompressed")
        names = set(apk.namelist())
        if "assets/_cl_" not in names:
            raise ValueError("assets/_cl_, the export's command line, is missing")
        missing = sorted(set(args.library) - names)
        if missing:
            raise ValueError("Missing native libraries: " + ", ".join(missing))
        definitions = apk_classes(apk) if args.java_class else set()
        classes = [name for name in args.java_class if name not in definitions]
        if classes:
            raise ValueError("Missing Java classes: " + ", ".join(classes))
        contents = pck_contents(apk.read("assets/main.pck"))
        missing_resources = sorted(set(args.pck_file) - set(contents["paths"]))
        if missing_resources:
            raise ValueError(f"PCK lacks resources: {missing_resources}")
        return {
            "application_id": args.application_id,
            "pck": contents,
            "native_libraries": sorted(
                name for name in names if name.startswith("lib/") and name.endswith(".so")
            ),
            "debug_symbols": check_symbols(apk, args) if args.debug_symbols else [],
        }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--bundletool", type=Path, required=True)
    parser.add_argument("--java", type=Path, required=True)
    parser.add_argument("--application-id", required=True)
    parser.add_argument(
        "--debug-symbols",
        type=Path,
        help="The application's debug symbol ZIP of <abi>/<name>.so entries.",
    )
    parser.add_argument(
        "--symbol-library",
        action="append",
        default=[],
        help="<abi>/<name>.so path the debug symbols must contain.",
    )
    parser.add_argument(
        "--debug-info",
        action="store_true",
        help="The debug symbols carry DWARF.",
    )
    parser.add_argument(
        "--library",
        action="append",
        default=[],
        help="APK path of a native library the bundle must deliver.",
    )
    parser.add_argument(
        "--manifest-entry",
        action="append",
        default=[],
        help="Text the bundle's base manifest must contain.",
    )
    parser.add_argument(
        "--java-class",
        action="append",
        default=[],
        help="Fully qualified Java class the APK's dex files must define.",
    )
    parser.add_argument(
        "--pck-file",
        action="append",
        default=[],
        help="Resource path the PCK must contain.",
    )
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="android-bundle-") as temporary:
        evidence = inspect(args, Path(temporary))
    outputs = os.environ.get("TEST_UNDECLARED_OUTPUTS_DIR")
    if outputs:
        Path(outputs, "bundle.json").write_text(json.dumps(evidence, indent=2) + "\n")
    print(
        "rules_godot: Android App Bundle verified:",
        json.dumps(evidence["native_libraries"]),
    )


if __name__ == "__main__":
    main()
