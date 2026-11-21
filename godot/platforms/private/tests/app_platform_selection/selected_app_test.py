"""
An application carries its platform's backend and libraries.

The application of one declaration contains the selected operating system's add-on
libraries and resources only, the engine and extension libraries of its CPUs, and the
feature tags of its environment.
"""

import argparse
import plistlib
import re
import struct
import subprocess
import sys
import tarfile
import tempfile
import unittest
import zipfile
from pathlib import Path

from tools.pck import pck_member, project_features, project_setting_keys
from tools.platforms.apple_bundle import bundle_files
from tools.platforms.native_symbols import require_slices

# The application's delivered artifact for each operating system.
PUBLISHED = {
    "android": {"app.apk", "app_unsigned.aab"},
    # Development builds keep the bundle a directory; distribution archives it.
    "ios": {"app.app", "app.ipa"},
    "macos": {"app.zip"},
    "linux": {"app.tar.gz"},
}

# Each operating system's add-on library places its own resource at a resource path of the
# project.
ADDON_RESOURCES = {
    "android": "main/libraries/android_addon.gd",
    "ios": "main/libraries/ios_addon.gd",
}


# A copy of the DEX reader of //godot/testing/private:inspect_android_bundle.py, whose
# library serves the public inspection helper only.
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


def packs(packed: bytes, path: str) -> bool:
    """Whether the PCK contains a file at the resource path."""
    try:
        pck_member(packed, path)
    except KeyError:
        return False
    return True


def read_files(path: Path, operating_system: str) -> dict[str, bytes]:
    """The files of an application archive or bundle by their path in it."""
    if path.name.endswith(".tar.gz"):
        files = {}
        with tarfile.open(path) as source:
            for member in source.getmembers():
                if member.isfile():
                    stream = source.extractfile(member)
                    assert stream is not None
                    files[member.name] = stream.read()
        return files
    if operating_system == "ios":
        return bundle_files(path)
    with zipfile.ZipFile(path) as source:
        return {
            name: source.read(name)
            for name in source.namelist()
            if not name.endswith("/")
        }


def inspect(args: argparse.Namespace) -> None:
    operating_system = args.operating_system
    cpus = set(args.cpus.split(","))
    environment = args.environment
    (path,) = [
        Path(output)
        for output in args.outputs
        if Path(output).name in PUBLISHED[operating_system]
    ]
    files = read_files(path, operating_system)
    assert files, "Application archive is empty"
    read_file = files.__getitem__
    names = list(files)
    pack_name = next(name for name in names if name.endswith(".pck"))
    packed = read_file(pack_name)
    settings = pck_member(packed, "project.binary")
    runtime_custom = project_features(settings)
    # Godot applies the .simulator override at runtime when the feature is present.
    assert "application/config/description.simulator" in project_setting_keys(settings)
    assert ("simulator" in runtime_custom) == (environment == "simulator"), runtime_custom
    assert not runtime_custom & {"arm64", "x86_64"}, runtime_custom
    for owner, resource in ADDON_RESOURCES.items():
        assert packs(packed, resource) == (owner == operating_system), (owner, resource)
    if operating_system != "ios":
        assert not any(name.endswith("/addon_notice.txt") for name in names), names
    if operating_system == "android":
        # sdk_bundle_test checks the AAB manifest with bundletool.
        if path.suffix == ".apk":
            manifest = subprocess.check_output(
                [args.aapt, "dump", "badging", str(path)], text=True
            )
            minimum = re.search(r"^sdkVersion:'(\d+)'", manifest, re.MULTILINE)
            target = re.search(r"^targetSdkVersion:'(\d+)'", manifest, re.MULTILINE)
            assert minimum and target, manifest
            assert (minimum[1], target[1]) == ("24", "36"), manifest
        classes = set().union(
            *(defined_classes(read_file(name)) for name in names if name.endswith(".dex"))
        )
        assert "org.example.addon.Addon" in classes, (
            "Selected project Java dependency missing"
        )
        assert "org.example.plugin.Plugin" in classes, "Selected project AAR missing"
        assert "androidx.core.splashscreen.SplashScreen" in classes, (
            "The internally provisioned splash screen is missing"
        )
        abis = {"arm64-v8a" if cpu == "arm64" else "x86_64" for cpu in cpus}
        extension = [name for name in names if name.endswith("/libhello_native.so")]
        assert {name.split("/")[-2] for name in extension} == abis, extension
        engine_libraries = [
            name for name in names if name.endswith("/libgodot_android.so")
        ]
        assert {name.split("/")[-2] for name in engine_libraries} == abis, (
            engine_libraries
        )
        for name in engine_libraries:
            require_slices(
                read_file(name),
                {"arm64" if name.split("/")[-2] == "arm64-v8a" else "x86_64"},
                "elf",
                name,
            )
    elif operating_system == "ios":
        plist_name = next(name for name in names if name.endswith(".app/Info.plist"))
        info = plistlib.loads(read_file(plist_name))
        assert info.get("GCSupportsControllerUserInteraction") is True, info
        assert any(name.endswith("/addon_notice.txt") for name in names), names
        assert not any(name.endswith((".dex", ".aar")) for name in names), names
        assert info["CFBundleIdentifier"] == "org.example.contract", info
        assert info["CFBundleExecutable"] == "app", info
        assert info["MinimumOSVersion"] == "15.0" and info["UIDeviceFamily"] == [
            1,
            2,
        ], info
        assert info["CFBundleSupportedPlatforms"] == [
            "iPhoneOS" if environment == "device" else "iPhoneSimulator"
        ], info
        bundle = plist_name.removesuffix("Info.plist")
        binary = bundle + info["CFBundleExecutable"]
        # The add-on's libraries link into the executable; the extension's library is
        # its own framework, which exports the entry symbol.
        framework = bundle + "Frameworks/hello.framework/hello"
        expected = {
            binary: ["rules_godot_example_controllers", "rules_godot_example_swift"],
            framework: ["rules_godot_library_init"],
        }
        with tempfile.TemporaryDirectory(prefix="godot-app-contents-") as directory:
            for name, wanted in expected.items():
                assert name in files, (name, names)
                require_slices(read_file(name), cpus, "ios_" + environment, name)
                image = Path(directory) / Path(name).name
                image.write_bytes(read_file(name))
                for cpu in sorted(cpus):
                    symbols = subprocess.check_output(
                        ["/usr/bin/nm", "-arch", cpu, "-U", str(image)], text=True
                    )
                    for symbol in wanted:
                        assert symbol in symbols, (cpu, name, symbol)
    else:
        binary = next(name for name in names if name.endswith("/app"))
        require_slices(
            read_file(binary),
            cpus,
            "macos" if operating_system == "macos" else "elf",
            binary,
        )
        descriptor = pck_member(packed, "native/hello.gdextension").decode()
        assert operating_system + "." in descriptor, descriptor
        assert any(name.endswith("/libhello_native.so") for name in names), names
        assert not any(name.endswith((".dex", ".aar")) for name in names), names


class SelectedAppTest(unittest.TestCase):
    def test_application_contains_its_platform_selection(self) -> None:
        parser = argparse.ArgumentParser()
        parser.add_argument(
            "--operating-system", choices=sorted(PUBLISHED), required=True
        )
        parser.add_argument("--cpus", required=True)
        parser.add_argument("--environment", default="none")
        parser.add_argument("--aapt")
        parser.add_argument("outputs", nargs="+")
        inspect(parser.parse_args(sys.argv[1:]))


if __name__ == "__main__":
    unittest.main(argv=sys.argv[:1])
