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


def package(
    output: str | Path, manifest: list[dict[str, str]], aar: str | Path | None = None
) -> None:
    """
    Write the JNI libraries as a ZIP, or the engine AAR: the Android shell library with
    the slot's engine library.

    An AAR's manifest names the version of source-built engine libraries, which
    must all name the same one.
    """
    entries: dict[str, bytes] = {}
    libraries: dict[str, Path] = {}
    if aar:
        with zipfile.ZipFile(aar) as source:
            for entry in source.infolist():
                if entry.is_dir():
                    continue
                path = PurePosixPath(entry.filename)
                if path.is_absolute() or ".." in path.parts:
                    raise ValueError("unsafe AAR entry: " + entry.filename)
                if (
                    len(path.parts) == 3
                    and path.parts[0] == "jni"
                    and path.name == "libgodot_android.so"
                ):
                    continue
                # Existing archive signatures cover the old contents.
                if path.parts[0] == "META-INF" and path.suffix.upper() in {
                    ".RSA",
                    ".SF",
                    ".DSA",
                }:
                    continue
                entries[entry.filename] = source.read(entry)
    versions = {version for library in manifest if (version := library_version(library))}
    if len(versions) > 1:
        raise ValueError(
            "The engine libraries name different versions: " + ", ".join(sorted(versions))
        )
    if aar and versions:
        entries["AndroidManifest.xml"] = set_library_version(
            entries["AndroidManifest.xml"].decode(), versions.pop()
        ).encode()
    for library in manifest:
        abi = library["abi"]
        if abi not in ABIS:
            raise ValueError("unsupported Android ABI: " + abi)
        name = library.get("name", Path(library["source"]).name)
        if (
            not name.startswith("lib")
            or not name.endswith(".so")
            or "/" in name
            or "\\" in name
        ):
            raise ValueError("Android native libraries must be named lib*.so: " + name)
        destination = ("jni/" if aar else "lib/") + abi + "/" + name
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
