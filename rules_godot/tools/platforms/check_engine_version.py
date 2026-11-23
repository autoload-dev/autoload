"""
Check that a packaged engine loads the pack, as Godot's pack loader decides.

Godot refuses a pack exported by a newer major.minor version. The Android
engine names its version in the AAR manifest's org.godotengine.library.version,
such as 4.8.0.beta or 4.7.2.stable.custom-git.<hash> for a source-built engine;
every engine library in its "Godot Engine v<version>" string, such as
4.8.beta1.official, and its hash in a string of its own. An engine that names
no version passes.

When the AAR manifest and the library it ships both name a version, they must
name the same engine: the version and status, and the build name and hash where
the manifest names them.

An engine also has to contain the code of the CPU it is linked or packaged
for: an Android AAR its engine library for the ABI, and the static libraries of an
iOS engine objects of the CPU and SDK.
"""

import argparse
import json
import mmap
import re
import zipfile
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import IO
from xml.etree import ElementTree

from tools.platforms.native_symbols import native_slices

ANDROID = "{http://schemas.android.com/apk/res/android}"
_LIBRARY_VERSION = re.compile(
    rb"Godot Engine v(\d+\.\d+(?:\.\d+)?\.[a-z]+\d*(?:\.[\w-]+)*)"
)
_ENGINE_LIBRARY = "libgodot_android.so"


@dataclass(frozen=True)
class Version:
    """An engine version as Godot names it."""

    numbers: tuple[int, ...]
    status: str
    build: str = ""
    digest: str = ""


def parse(text: str) -> Version:
    """
    Parse a version as a manifest or a library names it.

    A manifest always names the patch number and may add a build name and hash,
    such as 4.7.2.stable.custom-git.<hash>; a library omits a zero patch, such as
    4.8.beta1.official. Godot's module configuration, such as .mono, is skipped.
    """
    parts = text.split(".")
    count = 3 if len(parts) > 2 and parts[2].isdigit() else 2
    numbers = tuple(int(part) for part in parts[:count]) + (0,) * (3 - count)
    status, *rest = parts[count:]
    digest = rest.pop() if rest and re.fullmatch(r"[0-9a-f]{7,64}", rest[-1]) else ""
    return Version(numbers, status, rest[-1] if rest else "", digest)


def manifest_versions(path: Path) -> set[str]:
    """Return the library versions an Android manifest declares."""
    return {
        element.get(ANDROID + "value", "")
        for element in ElementTree.parse(path).getroot().iter("meta-data")
        if element.get(ANDROID + "name") == "org.godotengine.library.version"
    }


_CHUNK = 1 << 24
# Longer than any version string or hash: a match this close to the end of a
# chunk may continue in the next one, so it is searched again with that.
_OVERLAP = 128


def _chunks(source: IO[bytes]) -> Iterator[tuple[bytes, bool]]:
    """Yield overlapping chunks of a file and whether each one is its last."""
    tail = b""
    while chunk := source.read(_CHUNK):
        data = tail + chunk
        yield data, len(chunk) < _CHUNK
        tail = data[-_OVERLAP:]


def _scan(
    source: IO[bytes], hashes: frozenset[str] = frozenset()
) -> tuple[str, set[str]]:
    """
    Return the engine version a library names and which of the hashes it holds.

    Reads the library once, in chunks, and stops when it found both.
    """
    needles = {text.encode() + b"\0": text for text in hashes}
    version, found = "", set()
    for data, last in _chunks(source):
        match = None if version else _LIBRARY_VERSION.search(data)
        if match and (last or match.end() < len(data) - _OVERLAP):
            version = match.group(1).decode()
        found |= {text for needle, text in needles.items() if needle in data}
        if version and found == hashes:
            break
    return version, found


def library_versions(path: Path) -> set[str]:
    """Return the engine version a native library names, reading it in chunks."""
    with path.open("rb") as source:
        version, _ = _scan(source)
    return {version} if version else set()


def same_engine(manifest: Version, library: Version) -> bool:
    """
    Return whether a manifest names the engine its library names, hash aside.

    The manifest names a prerelease without its number, such as beta for beta1.
    """
    return (
        manifest.numbers == library.numbers
        and manifest.status.rstrip("0123456789") == library.status.rstrip("0123456789")
        and manifest.build in ("", library.build)
    )


def native_library_versions(path: Path, manifests: set[str]) -> set[str]:
    """
    Return the versions the engine libraries of an AAR's native libraries name.

    Fails when one names another engine than the AAR's manifest.
    """
    expected = {manifest: parse(manifest) for manifest in manifests}
    hashes = frozenset(v.digest for v in expected.values() if v.digest)
    found = set()
    with zipfile.ZipFile(path) as archive:
        for name in archive.namelist():
            if PurePosixPath(name).name != _ENGINE_LIBRARY:
                continue
            with archive.open(name) as source:
                library, held = _scan(source, hashes)
            if not library:
                continue
            for manifest, version in expected.items():
                if not same_engine(version, parse(library)):
                    raise SystemExit(
                        f"The engine AAR's manifest names Godot {manifest}, "
                        f"but its library is Godot {library}"
                    )
                if version.digest and version.digest not in held:
                    raise SystemExit(
                        f"The engine AAR's manifest names Godot {manifest}, "
                        f"but its library has no hash {version.digest}"
                    )
            found.add(library)
    return found


def engine_abis(path: Path) -> set[str]:
    """Return the ABIs for which native libraries ship Godot's engine library."""
    with zipfile.ZipFile(path) as archive:
        return {
            PurePosixPath(name).parent.name
            for name in archive.namelist()
            if PurePosixPath(name).name == _ENGINE_LIBRARY
        }


_IOS_ENVIRONMENTS = {"ios_device": "device", "ios_simulator": "Simulator"}
_IOS_EXPORT_PLATFORMS = {
    ("arm64", "ios_device"): "ios_arm64",
    ("arm64", "ios_simulator"): "ios_sim_arm64",
    ("x86_64", "ios_simulator"): "ios_sim_x86_64",
}


def require_ios_platform_slice(path: Path, cpu: str, sdk: str) -> None:
    """
    Fail unless a static library of an iOS engine has objects of cpu and sdk.

    An XCFramework can list a CPU its library lacks, such as the arm64 Simulator
    of Godot 4.7.2's templates; without this check, the link fails on missing
    symbols. A library without native objects is not decided.
    """
    if not path.stat().st_size:
        return
    with (
        path.open("rb") as source,
        mmap.mmap(source.fileno(), 0, access=mmap.ACCESS_READ) as data,
    ):
        slices = native_slices(data)
    if not slices or slices.get(cpu) in (sdk, ""):
        return
    available = sorted(
        (other, other_sdk)
        for other, other_sdk in slices.items()
        if other_sdk in _IOS_ENVIRONMENTS
    )
    names = ", ".join(
        f"{other} {_IOS_ENVIRONMENTS[other_sdk]}" for other, other_sdk in available
    )
    export_platforms = [
        "@autoload_rules_godot//godot/platforms:" + _IOS_EXPORT_PLATFORMS[pair]
        for pair in available
        if pair in _IOS_EXPORT_PLATFORMS
    ]
    requested = f"{cpu} {_IOS_ENVIRONMENTS[sdk]}"
    alternative = (
        f"Select an export platform it supports, such as {export_platforms[0]}, or use"
        if export_platforms
        else "Use"
    )
    raise SystemExit(
        f"The iOS engine library {path.name} has no {requested} slice; it has "
        f"{names or 'no iOS objects'}. {alternative} a source-built engine for "
        f"{requested}"
    )


_RENDERING_METHOD = "rendering/renderer/rendering_method"


def require_rendering_method(
    facts: Path, renderers: list[str], default: str = "forward_plus"
) -> None:
    """
    Fail when the pack's project asks for a rendering method its engine was built without.

    The facts hold the project setting with the export's feature overrides, such as the
    .mobile value for iOS and Android. Godot has no fallback for a method an engine lacks:
    the application fails at start.
    """
    settings = json.loads(facts.read_text(encoding="utf-8"))["settings"]
    method = settings.get(_RENDERING_METHOD, default)
    if method not in renderers:
        raise SystemExit(
            f"The project renders with {method}, but its engine runs only "
            + (", ".join(renderers) or "no renderer")
            + f"; set {_RENDERING_METHOD} for this platform to one of them, or build the "
            "engine with this method in its recipe's renderers"
        )


def _check_rendering_method(args: argparse.Namespace) -> None:
    """Check the project's rendering method where the engine declares its renderers."""
    if not args.facts or args.renderers is None:
        return
    # Godot's default for iOS and Android is the setting's .mobile override, mobile.
    mobile = args.ios_platform_slice or args.android_abi
    require_rendering_method(
        args.facts,
        [method for method in args.renderers.split(",") if method],
        "mobile" if mobile else "forward_plus",
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--android-manifest", type=Path, action="append", default=[])
    parser.add_argument(
        "--android-native-libs",
        type=Path,
        action="append",
        default=[],
        help="Native libraries zip of the AAR, whose engine library is compared.",
    )
    parser.add_argument(
        "--android-abi",
        help=(
            "ABI of the platform slice, such as arm64-v8a, whose engine library the "
            "AAR ships."
        ),
    )
    parser.add_argument("--library", type=Path, action="append", default=[])
    parser.add_argument(
        "--ios-library",
        type=Path,
        action="append",
        default=[],
        help=(
            "Static library of an iOS engine, which needs objects of "
            "--ios-platform-slice."
        ),
    )
    parser.add_argument(
        "--ios-platform-slice",
        help="CPU and SDK of the iOS platform slice, such as arm64:ios_simulator.",
    )
    parser.add_argument(
        "--assert-version",
        default="",
        help=(
            "Canonical declared version of a prebuilt engine, checked against inspected "
            "facts."
        ),
    )
    parser.add_argument(
        "--facts", type=Path, help="The pack's export facts, with its project settings."
    )
    parser.add_argument(
        "--renderers",
        help="Comma-separated rendering methods a source-built engine runs.",
    )
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main() -> None:
    parser = _parser()
    args = parser.parse_args()
    _check_rendering_method(args)
    manifests = set()
    for path in args.android_manifest:
        manifests |= manifest_versions(path)
    found = set(manifests)
    for path in args.library:
        if path.stat().st_size:
            found |= library_versions(path)
    for path in args.android_native_libs:
        found |= native_library_versions(path, manifests)
    if (
        args.android_abi
        and args.android_native_libs
        and not any(
            args.android_abi in engine_abis(path) for path in args.android_native_libs
        )
    ):
        raise SystemExit(
            f"The engine AAR has no {_ENGINE_LIBRARY} for {args.android_abi}; "
            "select an engine that supports the export platform's CPUs"
        )
    if args.ios_platform_slice:
        cpu, sdk = args.ios_platform_slice.split(":")
        # Report every library: together they show whether any export platform links.
        problems = []
        for path in args.ios_library:
            try:
                require_ios_platform_slice(path, cpu, sdk)
            except SystemExit as problem:
                problems.append(str(problem))
        if problems:
            raise SystemExit("\n".join(problems))
    if args.assert_version:
        expected = parse(
            args.assert_version.replace("-", ".")
            if "-" in args.assert_version
            else args.assert_version + ".stable"
        )
        for name in sorted(found):
            actual = parse(name)
            # A manifest omits the prerelease number; where a name has one, it must match.
            if not same_engine(expected, actual) or (
                any(c.isdigit() for c in actual.status)
                and actual.status != expected.status
            ):
                raise SystemExit(
                    f"engine_version assertion {args.assert_version} contradicts inspected engine {name}"
                )
    # The pack producer's version is never compared: editor and runtime are
    # selected independently and may differ in either direction.
    args.output.write_text(
        "Checked engine " + (", ".join(sorted(found)) or "without version facts") + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
