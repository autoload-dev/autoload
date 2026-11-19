"""Read the Android applications a library composition test builds."""

import argparse
import os
import struct
import subprocess
import zipfile
from pathlib import Path

from tools.platforms.native_symbols import elf_build_id, elf_sections


def bundle_tool_arguments(parser: argparse.ArgumentParser) -> None:
    """Add the tools that turn an App Bundle into its universal APK."""
    parser.add_argument("--bundletool", type=Path, required=True)
    parser.add_argument("--java", type=Path, required=True)


def apk(paths: list[str]) -> Path:
    """Return the signed APK among an APK application's default outputs."""
    (path,) = [
        Path(path)
        for path in paths
        if path.endswith(".apk") and not path.endswith("_unsigned.apk")
    ]
    return path


def dump(aapt: Path, apk_path: Path) -> tuple[str, str]:
    """Return the APK's manifest tree and its resource values as aapt prints them."""
    # The SDK's runner finds the tool beside the runfiles directory it starts in.
    manifest = subprocess.check_output(
        [aapt.absolute(), "dump", "xmltree", apk_path, "AndroidManifest.xml"], text=True
    )
    resources = subprocess.check_output(
        [aapt.absolute(), "dump", "--values", "resources", apk_path], text=True
    )
    return manifest, resources


def _run(command: list[str | Path], home: Path) -> str:
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


def universal_apk(args: argparse.Namespace, bundle: Path, work: Path) -> tuple[str, Path]:
    """Validate an App Bundle; return its base manifest and its universal APK."""
    bundletool = [args.java, "-jar", args.bundletool]
    _run([*bundletool, "validate", f"--bundle={bundle}"], work)
    manifest = _run([*bundletool, "dump", "manifest", f"--bundle={bundle}"], work)
    apks = work / "universal.apks"
    _run(
        [
            *bundletool,
            "build-apks",
            f"--bundle={bundle}",
            f"--output={apks}",
            "--mode=universal",
        ],
        work,
    )
    with zipfile.ZipFile(apks) as archive:
        archive.extract("universal.apk", work)
    return manifest, work / "universal.apk"


def _defined_classes(dex: bytes) -> set[str]:
    """Read defined class names from a little-endian DEX file's class_defs table."""
    # https://source.android.com/docs/core/runtime/dex-format#header-item
    if len(dex) < 112 or dex[:4] != b"dex\n":
        raise ValueError("Invalid DEX header")
    strings = struct.unpack_from("<I", dex, 60)[0]
    types = struct.unpack_from("<I", dex, 68)[0]
    class_count, classes = struct.unpack_from("<II", dex, 96)
    result = set()
    for index in range(class_count):
        type_index = struct.unpack_from("<I", dex, classes + index * 32)[0]
        string_index = struct.unpack_from("<I", dex, types + type_index * 4)[0]
        offset = struct.unpack_from("<I", dex, strings + string_index * 4)[0]
        # Skip the ULEB128 length of the MUTF-8 descriptor.
        while dex[offset] & 0x80:
            offset += 1
        offset += 1
        descriptor = dex[offset : dex.index(b"\0", offset)].decode("utf-8")
        result.add(descriptor[1:-1].replace("/", "."))
    return result


def apk_classes(apk_file: zipfile.ZipFile) -> set[str]:
    """Return the classes that the APK's DEX files define."""
    definitions = set()
    for name in apk_file.namelist():
        if name.startswith("classes") and name.endswith(".dex"):
            definitions |= _defined_classes(apk_file.read(name))
    return definitions


def debug_symbol_sections(
    apk_file: zipfile.ZipFile, symbols: Path
) -> dict[str, set[str]]:
    """
    Match each library of a debug symbol ZIP with the one the APK packages.

    Return the ELF section names of each unstripped library by its `<abi>/<name>.so`
    entry; raise when the APK lacks it, packages it unstripped, or the build IDs differ.
    """
    result = {}
    with zipfile.ZipFile(symbols) as archive:
        for name in sorted(archive.namelist()):
            unstripped = elf_sections(archive.read(name))
            packaged = elf_sections(apk_file.read("lib/" + name))
            build_id = elf_build_id(unstripped)
            if not build_id or build_id != elf_build_id(packaged):
                raise ValueError(f"{name}: the build IDs of package and symbols differ")
            if {".symtab", ".debug_info"} & set(packaged):
                raise ValueError(f"{name}: the APK packages it unstripped")
            result[name] = set(unstripped)
    return result
