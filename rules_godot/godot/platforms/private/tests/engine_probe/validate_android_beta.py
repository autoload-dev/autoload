"""
Inspect the APKs that the engine probe's tests build with the official and a source-built
Godot 4.8-beta1 engine.

The check proves package contents and signatures; it does not launch a device.
"""

import argparse
import configparser
import hashlib
import json
import re
import sys
import tempfile
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[5]))

from godot.platforms.private.tests.engine_probe.beta_probe import (
    BETA_COMMIT,
    check_cpp_configuration,
    cpp_descriptor,
    single_library,
    source_build_manifest,
)
from tools.digest import digest
from tools.pack.pck import pck_contents
from tools.platforms.native_symbols import elf_file_build_id
from tools.platforms.validate_artifacts import command

ENGINE_MEMBER = "lib/arm64-v8a/libgodot_android.so"
AAR_ENGINE_MEMBER = "jni/arm64-v8a/libgodot_android.so"
CPP_ENTRY = "example_library_init"


def check_cpp_descriptor(descriptor: configparser.ConfigParser) -> str:
    """Check the godot-cpp descriptor, and return the APK member of its library."""
    check_cpp_configuration(descriptor, CPP_ENTRY)
    library = single_library(
        descriptor,
        {"android", "arm64"},
        ".so",
        "godot-cpp descriptor must name one Android arm64 shared library",
    )
    return "lib/arm64-v8a/" + library.rsplit("/", 1)[-1]


def check_pack(data: bytes) -> tuple[dict[str, Any], str]:
    pack = pck_contents(data)
    if pack["godot_version"] != "4.8.0":
        raise ValueError(
            "Beta APK must contain a Godot 4.8.0 PCK, got " + pack["godot_version"]
        )
    return pack, check_cpp_descriptor(cpp_descriptor(pack, "APK"))


def engine_version(packaged: bytes, kind: str) -> str:
    origin = "official" if kind == "official" else "custom"
    # Upstream's release archive keeps version.py's status="beta"; official
    # binaries append the release number. The embedded commit identifies beta1
    # independently of that difference in version labels. A source-built engine names
    # its version hash instead, which covers the pinned beta1 archive.
    status = rb"beta1" if kind == "official" else rb"beta(?:1)?"
    version = re.search(rb"4\.8\." + status + rb"\." + origin.encode(), packaged)
    names_commit = kind != "official" or BETA_COMMIT.encode() in packaged
    if version is None or not names_commit:
        raise ValueError(
            "Packaged engine does not identify itself as Godot 4.8.beta1." + origin
        )
    return version.group().decode()


def check_source_engine(packaged: bytes, source: bytes | None) -> None:
    if source is None:
        raise ValueError(
            "Source-built engine validation requires the compiled engine library"
        )
    # The application packages the engine stripped as Bazel's --strip asks.
    if elf_file_build_id(packaged) != elf_file_build_id(source):
        raise ValueError("Packaged engine differs from the compiled source-built engine")
    if b"BazelProbe" not in source:
        raise ValueError(
            "Source-built engine does not contain the requested custom BazelProbe module"
        )
    if b"Godot Engine with Bazel patch" not in source:
        raise ValueError(
            "Source-built engine does not contain the expected engine-name patch"
        )


def check_engine(
    packaged: bytes, aar_engine_library: bytes, kind: str, source: bytes | None = None
) -> dict[str, Any]:
    version = engine_version(packaged, kind)
    if packaged != aar_engine_library:
        raise ValueError("Packaged engine differs from the selected engine AAR")
    if kind == "source":
        check_source_engine(packaged, source)
    result = {
        "version_string": version,
        "commit": BETA_COMMIT,
        "sha256": hashlib.sha256(packaged).hexdigest(),
        "matches_selected_aar": True,
    }
    if kind == "source":
        result.update(matches_compiled_source_library=True, custom_module="BazelProbe")
    return result


def check_symbols(symbols: str, entry: str) -> None:
    for line in symbols.splitlines():
        fields = line.split()
        if len(fields) >= 8 and fields[-1] == entry and fields[-2] != "UND":
            return
    raise ValueError("Packaged godot-cpp extension does not export " + entry)


def check_cpp_library(tool: Path, data: bytes, library: Path) -> None:
    """Check the packaged godot-cpp library, written to a file for readelf."""
    if b"BazelNode" not in data:
        raise ValueError(
            "Packaged godot-cpp extension does not contain the BazelNode implementation"
        )
    library.write_bytes(data)
    check_symbols(command([tool, "--dyn-syms", "--wide", library]), CPP_ENTRY)
    header = command([tool, "--file-header", library])
    if not re.search(r"Machine:\s+AArch64", header):
        raise ValueError("Android godot-cpp extension is not an AArch64 ELF library")


# The lines of aapt's badging that the report keeps.
MANIFEST_SUMMARY = (
    "package:",
    "sdkVersion:",
    "targetSdkVersion:",
    "launchable-activity:",
    "native-code:",
)


def verify(args: argparse.Namespace) -> dict[str, Any]:
    with zipfile.ZipFile(args.engine_aar) as archive:
        aar_engine_library = archive.read(AAR_ENGINE_MEMBER)
    with (
        zipfile.ZipFile(args.artifact) as archive,
        tempfile.TemporaryDirectory(prefix="godot-android-beta-") as temporary,
    ):
        pack, cpp_member = check_pack(archive.read("assets/main.pck"))
        engine = check_engine(
            archive.read(ENGINE_MEMBER),
            aar_engine_library,
            args.kind,
            args.source_library.read_bytes() if args.source_library else None,
        )
        cpp_data = archive.read(cpp_member)
        check_cpp_library(args.readelf, cpp_data, Path(temporary) / Path(cpp_member).name)
        badging = command([args.aapt, "dump", "badging", args.artifact])
        signature = command([args.apksigner, "verify", "--verbose", args.artifact])
        native_paths = sorted(
            path
            for path in archive.namelist()
            if path.startswith("lib/") and path.endswith(".so")
        )
    result = {
        "validated_at_utc": datetime.now(UTC).isoformat(),
        "operating_system": "android",
        "engine_kind": args.kind,
        "artifact": str(args.artifact),
        "sha256": digest(args.artifact),
        "size_bytes": args.artifact.stat().st_size,
        "engine": engine,
        "pck": pack,
        "godot_cpp": {
            "release": "10.0.0-stable",
            "api": "4.7",
            "compatibility_minimum": "4.7.2",
            "packaged_library": cpp_member,
            "sha256": hashlib.sha256(cpp_data).hexdigest(),
            "exported_entry": CPP_ENTRY,
            "class_implementation": "BazelNode",
        },
        "native_libraries": native_paths,
        "signature_verification": signature,
        "manifest_summary": [
            line for line in badging.splitlines() if line.startswith(MANIFEST_SUMMARY)
        ],
        "device_execution": False,
    }
    if args.engine_manifest:
        result["engine_manifest"] = source_build_manifest(
            args.engine_manifest, "android", "Android"
        )
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--artifact",
        type=Path,
        required=True,
        help="Built beta_app.apk or beta_source_built_app.apk",
    )
    parser.add_argument("--kind", choices=["official", "source"], required=True)
    parser.add_argument(
        "--engine-aar",
        type=Path,
        required=True,
        help=(
            "Selected engine AAR of the official or the source-built engine; its engine"
            " library must match the APK"
        ),
    )
    parser.add_argument(
        "--source-library",
        type=Path,
        help="Engine library of the source-built engine; required for --kind=source",
    )
    parser.add_argument("--engine-manifest", type=Path)
    parser.add_argument("--aapt", type=Path, required=True)
    parser.add_argument("--apksigner", type=Path, required=True)
    parser.add_argument("--readelf", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.kind == "source" and args.source_library is None:
        parser.error("--kind=source requires --source-library")
    result = verify(args)
    text = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(text)
        print(args.output)
    else:
        print(text, end="")


if __name__ == "__main__":
    main()
