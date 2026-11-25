"""
Derive an application's runtime profile from its project, and keep it in the checkout.

A runtime profile is what an application's runtime can leave out: the engine classes and
build options that the project's scenes, resources and scripts do not use. The derivation
runs the editor of the selected engine headless over the project, lets Godot's own
detection of the Engine Compilation Configuration editor ("Detect from Project") write a
build profile, and composes the result: Godot's profile without the classes of the keep
list. It writes one `.gdbuild`, as Godot writes it, which `godot_app`'s `build_profile`
takes and the module extension reads for its build options.

`bazel run` writes the file into the checkout; `bazel test` fails while it no longer matches
the derivation. The derivation is a build action, so Bazel caches it with the project's
imports and the editor.

Sections: Composition, Derivation, Sync.
"""

import argparse
import difflib
import json
import os
import shutil
import sys
from collections.abc import Collection, Mapping
from pathlib import Path
from typing import Any

from godot.private.project_config import enable_plugins
from tools.godot_run import report, runfile_locator
from tools.godot_staging import (
    add_manifest_arguments,
    join_action,
    load_manifest,
    run_action,
    staged_project,
)


class ProfileError(Exception):
    """The derivation or composition of a runtime profile failed."""


# ==== Composition =============================================================


def compose_profile(
    detected: Mapping[str, Any],
    keep: Collection[str],
    unknown_options: Collection[str] = (),
    implied_options: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """
    Compose the runtime profile from Godot's detection.

    Args:
        detected: The build profile Godot's detection wrote: `disabled_classes` and
            `disabled_build_options`, which holds module switches such as
            `module_openxr_enabled` beside the SCons options.
        keep: Classes the profile never disables, whatever the detection found.
        unknown_options: Options Godot's editor writes that the same version's build
            does not have, such as rendering_device in 4.7; the profile leaves them out.
        implied_options: Option -> the options its build needs beside it, such as a
            module that fails to compile without it; added where the option is set.

    Returns:
        Godot's profile with the classes of the keep list removed and its classes sorted,
        its options without the unknown ones and with the implied ones.

    Raises:
        ProfileError: The detection lacks a field.
    """
    classes = detected.get("disabled_classes")
    options = detected.get("disabled_build_options")
    if not isinstance(classes, list) or not isinstance(options, dict):
        raise ProfileError(
            "Godot's profile has no disabled_classes and disabled_build_options"
        )
    composed = {
        name: value for name, value in options.items() if name not in unknown_options
    }
    for name in list(composed):
        composed |= (implied_options or {}).get(name, {})
    return {
        "type": "build_profile",
        "disabled_classes": sorted(set(classes) - set(keep)),
        "disabled_build_options": dict(sorted(composed.items())),
    }


def render_profile(profile: Mapping[str, Any]) -> str:
    """The `.gdbuild` text: Godot's own layout, sorted keys indented by tabs."""
    return json.dumps(profile, indent="\t", sort_keys=True) + "\n"


# ==== Derivation ==============================================================

_PLUGIN = Path(__file__).parent / "profile"

_PLUGIN_DIRECTORY = "addons/rules_godot_profile"


def _join_plugin(root: Path) -> None:
    """Stage the profile plugin next to the action plugin and enable it."""
    directory = root / _PLUGIN_DIRECTORY
    shutil.copytree(_PLUGIN, directory)
    (directory / ".gdignore").touch()
    project = root / "project.godot"
    project.write_text(
        enable_plugins(
            project.read_text(encoding="utf-8"),
            [f"res://{_PLUGIN_DIRECTORY}/plugin.cfg"],
        ),
        encoding="utf-8",
    )


def derive(manifest: dict, output: Path, execroot: Path) -> None:
    """
    Derive the runtime profile with the manifest's editor and write it as a `.gdbuild`.

    Args:
        manifest: The action manifest: the staged project and `keep_classes`.
        output: The `.gdbuild` file to write.
        execroot: The execution root, which the manifest's paths are relative to.

    Raises:
        ProfileError: Godot wrote no profile.
    """
    with staged_project(manifest, execroot, "godot-profile-") as (work, root, _):
        detected_path = work / "detected.gdbuild"
        join_action(root, work, "profile", {"profile": str(detected_path)})
        _join_plugin(root)
        # The plugin records its result when Godot's detection has finished.
        record = run_action(manifest, execroot, root, work, ["--editor"])
        if not detected_path.is_file():
            raise ProfileError(f"Godot wrote no profile:\n{record['output']}")
        detected = json.loads(detected_path.read_text(encoding="utf-8"))
    profile = compose_profile(
        detected,
        manifest["keep_classes"],
        manifest.get("unknown_options", ()),
        manifest.get("implied_options", {}),
    )
    output.write_text(render_profile(profile), encoding="utf-8")


def _derive(arguments: list[str]) -> None:
    parser = argparse.ArgumentParser(description="Derive a runtime profile.")
    add_manifest_arguments(parser)
    args = parser.parse_args(arguments)
    try:
        derive(load_manifest(args), args.output.absolute(), Path.cwd())
    except ProfileError as error:
        sys.exit(str(error))


# ==== Sync ====================================================================

# How many lines of a difference the test names.
_DIFF_LINES = 24


def place_files(entries: list[dict], workspace: Path) -> None:
    """
    Write the derived files into the checkout.

    Args:
        entries: One per file: `built`, the derived file, and `target`, its path in
            the checkout relative to the workspace.
        workspace: The checkout's root directory.
    """
    for entry in entries:
        built: Path = entry["built"]
        destination = workspace / entry["target"]
        if destination.is_file() and destination.read_bytes() == built.read_bytes():
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(built, destination)
        report(f"wrote {entry['target']}; commit it")


def check_files(entries: list[dict], writer: str) -> int:
    """
    Name each checked-in file that is missing or does not match the derivation.

    Args:
        entries: One per file: `built`, `checked_in` (None for a missing file) and `target`.
        writer: The label whose `bazel run` writes the files.

    Returns:
        1 if any file is missing or stale, else 0.
    """
    status = 0
    for entry in entries:
        target = entry["target"]
        if entry["checked_in"] is None:
            report(f"{target} is missing; write it with bazel run {writer}")
            status = 1
            continue
        built = entry["built"].read_text(encoding="utf-8").splitlines(keepends=True)
        checked = (
            entry["checked_in"].read_text(encoding="utf-8").splitlines(keepends=True)
        )
        if built == checked:
            continue
        difference = list(
            difflib.unified_diff(checked, built, "checked in", "derived", n=1)
        )
        shown = "".join(difference[:_DIFF_LINES])
        more = len(difference) - _DIFF_LINES
        report(
            f"{target} does not match the derivation; write it with bazel run {writer}:\n"
            + shown
            + (f"... {more} more lines\n" if more > 0 else "")
        )
        status = 1
    return status


def _sync(manifest_path: Path) -> None:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    runfile = runfile_locator(manifest["workspace"])
    entries = [
        {
            "built": runfile(each["built"]),
            "checked_in": runfile(each["checked_in"]) if each["checked_in"] else None,
            "target": each["target"],
        }
        for each in manifest["files"]
    ]
    if manifest["test"]:
        raise SystemExit(check_files(entries, manifest["writer"]))
    workspace = os.environ.get("BUILD_WORKSPACE_DIRECTORY")
    if not workspace:
        report("write the runtime profile with bazel run")
        raise SystemExit(1)
    place_files(entries, Path(workspace))


def main() -> None:
    if sys.argv[1:2] == ["derive"]:
        _derive(sys.argv[2:])
        return
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    _sync(parser.parse_args().manifest)


if __name__ == "__main__":
    main()
