"""
Inspect iOS artifacts of the official and a source-built Godot 4.8-beta1 engine without
launching them.

Official beta1 has incompatible simulator slices across its bundled Godot and
AccessKit XCFrameworks. Its arm64 device executable can be checked without a
provisioning profile; the source-built engine's Simulator app of the engine probe's
tests supplies a signed app.
"""

import argparse
import configparser
import hashlib
import json
import plistlib
import re
import subprocess
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[5]))

from tools.digest import digest
from tools.pack.pck import pck_contents
from tools.platforms.apple_bundle import application_bundle, bundle_identity
from tools.platforms.validate_artifacts import command

BETA_COMMIT = "4d10419cacd6d3009976e8f9fd3abd970fd58018"
CPP_ENTRY = "_example_library_init"
ACCESSKIT_ENTRIES = ["_accesskit_node_new", "_accesskit_ios_subclassing_adapter_new"]


def check_mode(kind: str, environment: str, package: bool) -> None:
    if not package and (kind != "official" or environment != "device"):
        raise ValueError(
            "Separate executable validation is restricted to the official device link"
        )


def check_pack(data: bytes) -> dict[str, Any]:
    pack = pck_contents(data, include_paths=True)
    if pack["godot_version"] != "4.8.0":
        raise ValueError(
            "Beta IPA must contain a Godot 4.8.0 PCK, got " + pack["godot_version"]
        )
    descriptor = configparser.ConfigParser(interpolation=None)
    path = "native/cpp_example.gdextension"
    if path not in pack["extension_descriptors"]:
        raise ValueError("Beta IPA has no godot-cpp extension descriptor")
    descriptor.read_string(pack["extension_descriptors"][path])
    if json.loads(descriptor["configuration"]["entry_symbol"]) != CPP_ENTRY.removeprefix(
        "_"
    ):
        raise ValueError("godot-cpp descriptor names an unexpected entry symbol")
    if json.loads(descriptor["configuration"]["compatibility_minimum"]) != "4.7.2":
        raise ValueError(
            "The Beta example must retain its Godot 4.7.2 extension compatibility minimum"
        )
    libraries = [
        json.loads(value)
        for tags, value in descriptor["libraries"].items()
        if {"ios", "arm64"}.issubset(tags.split("."))
    ]
    if (
        len(libraries) != 1
        or not libraries[0].startswith("res://")
        or not libraries[0].endswith(".a")
    ):
        raise ValueError(
            "godot-cpp descriptor must retain one nonempty iOS arm64 static .a path"
        )
    if any(
        path.removeprefix("res://").startswith("native/bin/") for path in pack["paths"]
    ):
        raise ValueError(
            "iOS PCK must exclude extension libraries; static extension libraries resolve "
            "from the linked executable"
        )
    return pack


def check_sdk(commands: str, environment: str) -> str:
    blocks = re.findall(
        r"cmd LC_BUILD_VERSION\b(.*?)(?=Load command|\Z)", commands, flags=re.DOTALL
    )
    values = [re.search(r"\bplatform\s+(\S+)", block) for block in blocks]
    sdks = [match[1] for match in values if match]
    allowed = {"2", "IOS"} if environment == "device" else {"7", "IOSSIMULATOR"}
    if len(sdks) != 1 or sdks[0] not in allowed:
        raise ValueError("Mach-O SDK does not match the expected iOS " + environment)
    if "cmd LC_MAIN" not in commands:
        raise ValueError("iOS executable is missing the SwiftUI main entry point")
    return blocks[0].strip()


def check_export(symbols: str, entry: str) -> None:
    if not any(
        line.split() and line.split()[-1] == entry for line in symbols.splitlines()
    ):
        raise ValueError("Linked iOS executable does not define/export " + entry)


def check_bootstrap(plist: dict[str, Any]) -> None:
    if not plist.get("UIApplicationSceneManifest"):
        raise ValueError("Godot iOS app is missing its SwiftUI scene manifest")


def engine_version(data: bytes, kind: str) -> str:
    status = rb"beta1" if kind == "official" else rb"beta(?:1)?"
    origin = b"official" if kind == "official" else b"custom"
    pattern = rb"4\.8\." + status + rb"\." + origin
    version = re.search(pattern, data)
    # A source-built engine names its version hash instead of the commit; the hash covers
    # the pinned beta1 archive.
    if version is None or kind == "official" and BETA_COMMIT.encode() not in data:
        raise ValueError(
            "iOS engine bytes do not identify the selected Godot 4.8-beta1 commit and engine kind"
        )
    if kind == "source" and (
        b"BazelProbe" not in data or b"Godot Engine with Bazel patch" not in data
    ):
        raise ValueError(
            "iOS source-built engine must contain the custom module and engine-name patch"
        )
    return version.group().decode()


def accesskit_symbols(library: Path, directory: Path) -> tuple[str, list[str]]:
    # Apple's nm cannot read three unrelated compiler-builtins objects emitted
    # by this beta's newer Rust LLVM. Inspect the actual AccessKit crate object
    # instead, and let every tool failure remain fatal. The linked executable
    # is inspected separately, including its undefined symbols.
    members = [
        name
        for name in command(["/usr/bin/xcrun", "ar", "-t", library]).splitlines()
        if name.startswith("accesskit.") and name.endswith(".o")
    ]
    if not members:
        raise ValueError(
            "Selected AccessKit archive contains no compiled AccessKit crate object"
        )
    definitions = []
    for index, member in enumerate(members):
        path = directory / f"accesskit-{index}.o"
        path.write_bytes(
            subprocess.check_output(["/usr/bin/xcrun", "ar", "-p", str(library), member])
        )
        definitions.append(command(["/usr/bin/xcrun", "nm", "-g", "-U", path]))
    return "\n".join(definitions), members


def source_build_manifest(path: Path) -> dict:
    """Return the source-built engine's manifest after checking what it was built from."""
    manifest = json.loads(path.read_text())
    if (
        manifest.get("version") not in {"4.8.0-beta", "4.8.0-beta1"}
        or manifest.get("platform") != "ios"
    ):
        raise ValueError(
            "Source-built engine manifest does not describe Godot 4.8 Beta for iOS"
        )
    if "bazel_probe" not in manifest.get("selected_modules", []):
        raise ValueError(
            "Source-built engine manifest is missing the custom bazel_probe module"
        )
    if not manifest.get("build_profile_scoped"):
        raise ValueError(
            "Every source of the source-built engine sees the build profile: its "
            "class_db.h no longer matches tools/engine/build_profile.py"
        )
    return manifest


def verify(args: argparse.Namespace) -> dict[str, Any]:
    check_mode(args.kind, args.expected_environment, args.artifact is not None)
    # Read the actual selected engine libraries. A source-built engine consists
    # of multiple per-configuration archives; no empty wrapper archive qualifies.
    libraries, library_bytes = [], []
    for path in args.engine_library:
        data = path.read_bytes()
        cpus = command(["/usr/bin/xcrun", "lipo", "-archs", path]).split()
        if "arm64" not in cpus:
            raise ValueError("Selected engine archive has no arm64 slice: " + str(path))
        libraries.append(
            {
                "path": str(path),
                "sha256": hashlib.sha256(data).hexdigest(),
                "size_bytes": len(data),
                "cpus": cpus,
            }
        )
        library_bytes.append(data)
    archive_version = engine_version(b"".join(library_bytes), args.kind)
    with tempfile.TemporaryDirectory(prefix="godot-ios-beta-") as temporary:
        temporary = Path(temporary)
        app = None
        if args.artifact:
            app = application_bundle(args.artifact, temporary)
            plist = plistlib.loads((app / "Info.plist").read_bytes())
            executable_name = plist["CFBundleExecutable"]
            if Path(executable_name).name != executable_name:
                raise ValueError("Unsafe application executable name")
            executable = app / executable_name
            pck = app / (executable_name + ".pck")
        else:
            executable = args.binary
            plist = plistlib.loads(args.plist.read_bytes())
            pck = args.pack
        executable_bytes = executable.read_bytes()
        version = engine_version(executable_bytes, args.kind)
        if version != archive_version:
            raise ValueError(
                "Linked iOS engine version does not match the selected engine archives"
            )
        cpus = command(["/usr/bin/xcrun", "lipo", "-archs", executable]).split()
        if cpus != ["arm64"]:
            raise ValueError("Beta iOS validation expects an arm64 executable")
        commands = command(["/usr/bin/xcrun", "otool", "-l", executable])
        platform_build = check_sdk(commands, args.expected_environment)
        check_bootstrap(plist)
        exports = command(["/usr/bin/xcrun", "dyld_info", "-exports", executable])
        check_export(exports, CPP_ENTRY)
        check_export(exports, "_rules_godot_library_init")
        if b"BazelNode" not in executable_bytes:
            raise ValueError("Linked godot-cpp BazelNode implementation is absent")
        undefined = command(["/usr/bin/xcrun", "nm", "-u", executable])
        if re.search(r"\b_accesskit_", undefined):
            raise ValueError("Linked iOS app still has unresolved AccessKit FFI symbols")
        accesskit = None
        if args.kind == "official":
            if args.accesskit_library is None:
                raise ValueError(
                    "Official iOS validation requires the selected AccessKit archive"
                )
            accesskit_definitions, members = accesskit_symbols(
                args.accesskit_library, temporary
            )
            # The linker hides AccessKit's static FFI definitions. Local `t`
            # symbols still prove that upstream implementations were linked.
            definitions = command(["/usr/bin/xcrun", "nm", "-U", executable])
            for entry in ACCESSKIT_ENTRIES:
                check_export(accesskit_definitions, entry)
                check_export(definitions, entry)
            accesskit = {
                "path": str(args.accesskit_library),
                "sha256": digest(args.accesskit_library),
                "inspected_crate_objects": members,
                "defined_ffi_symbols": ACCESSKIT_ENTRIES,
            }
        pack = check_pack(pck.read_bytes())
        if app is None:
            signature = (
                "Not performed: device executable link, not a signed application package"
            )
        else:
            signed = subprocess.run(
                ["/usr/bin/codesign", "--verify", "--deep", "--strict", app],
                capture_output=True,
                text=True,
                check=False,
            )
            if signed.returncode == 0:
                signature = "codesign --verify --deep --strict passed"
            else:
                raise ValueError(
                    "iOS code signature verification failed: "
                    + signed.stdout
                    + signed.stderr
                )
        artifact = args.artifact or args.binary
        sha256, size = bundle_identity(artifact)
        result = {
            "validated_at_utc": datetime.now(UTC).isoformat(),
            "operating_system": "ios",
            "engine_kind": args.kind,
            "artifact": str(artifact),
            "artifact_kind": "ios_application"
            if args.artifact
            else "device_executable_link",
            "package_validated": args.artifact is not None,
            "sha256": sha256,
            "size_bytes": size,
            "binary": {
                "cpus": cpus,
                "environment": args.expected_environment,
                "platform_build": platform_build,
                "sha256": hashlib.sha256(executable_bytes).hexdigest(),
                "engine_version_string": version,
            },
            "engine_commit": BETA_COMMIT,
            "selected_engine_libraries": libraries,
            "pck": pack,
            "godot_cpp": {
                "release": "10.0.0-stable",
                "api": "4.7",
                "compatibility_minimum": "4.7.2",
                "static_entry_exported": CPP_ENTRY,
                "class_implementation": "BazelNode",
            },
            "swiftui_scene_manifest_present": True,
            "signature_verification": signature,
            "unresolved_accesskit_symbols": [],
            "device_execution": False,
            "simulator_launch": False,
        }
        if app is None:
            result["separate_resources"] = {
                "pck": str(pck),
                "pck_sha256": digest(pck),
                "bootstrap_plist": str(args.plist),
                "bootstrap_plist_sha256": digest(args.plist),
            }
        if accesskit:
            result["accesskit"] = accesskit
    if args.engine_manifest:
        result["engine_manifest"] = source_build_manifest(args.engine_manifest)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    artifact = parser.add_mutually_exclusive_group(required=True)
    artifact.add_argument(
        "--artifact", type=Path, help="Built simulator or device app or IPA"
    )
    artifact.add_argument(
        "--binary",
        type=Path,
        help="Official arm64 device executable link; package validation is not claimed",
    )
    parser.add_argument(
        "--pack", type=Path, help="Separate Beta PCK, required with --binary"
    )
    parser.add_argument(
        "--plist",
        type=Path,
        help="Generated bootstrap Godot.plist, required with --binary",
    )
    parser.add_argument("--kind", choices=["official", "source"], required=True)
    parser.add_argument(
        "--expected-environment", choices=["device", "simulator"], required=True
    )
    parser.add_argument(
        "--engine-library",
        type=Path,
        action="extend",
        nargs="+",
        required=True,
        help=(
            "Actual selected engine libraries; accepts a source compile-group glob or "
            "repeated options"
        ),
    )
    parser.add_argument(
        "--accesskit-library",
        type=Path,
        help="Actual selected AccessKit archive; required for the prebuilt engine",
    )
    parser.add_argument("--engine-manifest", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if sys.platform != "darwin":
        parser.error(
            "iOS artifact validation requires the installed Xcode command-line tools"
        )
    if args.binary and (not args.pack or not args.plist):
        parser.error("--binary requires --pack and --plist")
    try:
        check_mode(args.kind, args.expected_environment, args.artifact is not None)
    except ValueError as error:
        parser.error(str(error))
    result = verify(args)
    text = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(text)
        print(args.output)
    else:
        print(text, end="")


if __name__ == "__main__":
    main()
