"""
What the Android and iOS checks of the Godot 4.8-beta1 engine probe share: the beta commit,
the godot-cpp extension descriptor in the pack, and the manifest of a source-built engine.
"""

import configparser
import json
from pathlib import Path
from typing import Any

BETA_COMMIT = "4d10419cacd6d3009976e8f9fd3abd970fd58018"

CPP_DESCRIPTOR = "native/cpp_example.gdextension"


def cpp_descriptor(pack: dict[str, Any], artifact: str) -> configparser.ConfigParser:
    """Return the pack's godot-cpp descriptor; artifact names the package, such as APK."""
    if CPP_DESCRIPTOR not in pack["extension_descriptors"]:
        raise ValueError(f"Beta {artifact} has no godot-cpp extension descriptor")
    descriptor = configparser.ConfigParser(interpolation=None)
    descriptor.read_string(pack["extension_descriptors"][CPP_DESCRIPTOR])
    return descriptor


def check_cpp_configuration(descriptor: configparser.ConfigParser, entry: str) -> None:
    """Check the descriptor's entry symbol and its Godot 4.7.2 compatibility minimum."""
    configuration = descriptor["configuration"]
    if json.loads(configuration["entry_symbol"]) != entry:
        raise ValueError("godot-cpp descriptor names an unexpected entry symbol")
    if json.loads(configuration["compatibility_minimum"]) != "4.7.2":
        raise ValueError(
            "The Beta example must retain its Godot 4.7.2 extension compatibility minimum"
        )


def single_library(
    descriptor: configparser.ConfigParser, tags: set[str], suffix: str, error: str
) -> str:
    """Return the one library of the feature tags, a res:// path ending in suffix."""
    libraries = [
        json.loads(value)
        for name, value in descriptor["libraries"].items()
        if tags.issubset(name.split("."))
    ]
    if len(libraries) != 1 or not (
        libraries[0].startswith("res://") and libraries[0].endswith(suffix)
    ):
        raise ValueError(error)
    return libraries[0]


def source_build_manifest(path: Path, platform: str, name: str) -> dict:
    """
    Return the source-built engine's manifest after checking what it was built from.

    platform is the manifest's platform, such as ios; name is how messages call it.
    """
    manifest = json.loads(path.read_text())
    if (
        manifest.get("version") not in {"4.8.0-beta", "4.8.0-beta1"}
        or manifest.get("platform") != platform
    ):
        raise ValueError(
            f"Source-built engine manifest does not describe Godot 4.8 Beta for {name}"
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
