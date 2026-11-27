"""Write JNI libraries as a normalized ZIP, or the engine AAR of an Android shell library."""

import argparse
import json
import re
import zipfile
from pathlib import Path, PurePosixPath

from tools.platforms.zip_archive import write_zip

ABIS = {"arm64-v8a", "armeabi-v7a", "x86", "x86_64"}

_LIBRARY_VERSION = re.compile(
    r'(<meta-data\s[^>]*?android:name="org\.godotengine\.library\.version"'
    r'[^>]*?android:value=")[^"]*(")'
)


def set_library_version(manifest: str, version: str) -> str:
    """Return an AAR manifest that names the engine version it ships."""
    replaced, count = _LIBRARY_VERSION.subn(
        lambda match: match.group(1) + version + match.group(2), manifest
    )
    if count != 1:
        raise ValueError(
            "The AAR manifest must declare org.godotengine.library.version once, "
            "with android:name before android:value"
        )
    return replaced


def library_version(library: dict[str, str]) -> str | None:
    """
    Return the version a source-built engine library names, such as
    4.7.2.stable.custom-git.<hash>, from its version and build and hash files.
    """
    if "version" not in library:
        return None
    build, hash_ = (
        Path(library[key]).read_text(encoding="utf-8") for key in ("build", "hash")
    )
    return f"{library['version']}.{build}.{hash_}"


# Archive signatures, which cover the shell library's old contents.
_SIGNATURES = {".RSA", ".SF", ".DSA"}


def _kept(path: PurePosixPath) -> bool:
    """Whether an entry of the shell library stays in the engine AAR."""
    if path.full_match("jni/*/libgodot_android.so"):
        return False
    return not (path.parts[0] == "META-INF" and path.suffix.upper() in _SIGNATURES)


def _shell_entries(aar: str | Path) -> dict[str, bytes]:
    """Return the files of the shell library without its engine libraries and signatures."""
    entries = {}
    with zipfile.ZipFile(aar) as source:
        for entry in source.infolist():
            if entry.is_dir():
                continue
            path = PurePosixPath(entry.filename)
            if path.is_absolute() or ".." in path.parts:
                raise ValueError("unsafe AAR entry: " + entry.filename)
            if _kept(path):
                entries[entry.filename] = source.read(entry)
    return entries


# Android's package manager installs only native libraries named lib*.so.
_LIBRARY_NAME = re.compile(r"lib[^/\\]*\.so")


def _library_name(library: dict[str, str]) -> str:
    """Return the file name of a native library, lib*.so."""
    name = library.get("name", Path(library["source"]).name)
    if not _LIBRARY_NAME.fullmatch(name):
        raise ValueError("Android native libraries must be named lib*.so: " + name)
    return name


def _source_built_version(manifest: list[dict[str, str]]) -> str | None:
    """Return the version the source-built engine libraries name, which must be one."""
    versions = {version for library in manifest if (version := library_version(library))}
    if len(versions) > 1:
        raise ValueError(
            "The engine libraries name different versions: " + ", ".join(sorted(versions))
        )
    return versions.pop() if versions else None


def package(
    output: str | Path, manifest: list[dict[str, str]], aar: str | Path | None = None
) -> None:
    """
    Write the JNI libraries as a ZIP, or the engine AAR: the Android shell library with
    the slot's engine library.

    An AAR's manifest names the version of source-built engine libraries, which
    must all name the same one.
    """
    entries = _shell_entries(aar) if aar else {}
    version = _source_built_version(manifest)
    if aar and version:
        entries["AndroidManifest.xml"] = set_library_version(
            entries["AndroidManifest.xml"].decode(), version
        ).encode()
    libraries: dict[str, Path] = {}
    for library in manifest:
        abi = library["abi"]
        if abi not in ABIS:
            raise ValueError("unsupported Android ABI: " + abi)
        destination = ("jni/" if aar else "lib/") + abi + "/" + _library_name(library)
        if destination in entries or destination in libraries:
            raise ValueError("duplicate Android library: " + destination)
        libraries[destination] = Path(library["source"])
    write_zip(output, entries | libraries)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--aar")
    args = parser.parse_args()
    package(args.output, json.loads(Path(args.manifest).read_text()), args.aar)


if __name__ == "__main__":
    main()
