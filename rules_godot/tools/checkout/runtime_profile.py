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
import shutil
import sys
from collections.abc import Collection, Mapping
from pathlib import Path
from typing import Any

from tools.checkout.sync import Runfile, report, sync_main
from tools.editor_action.action import join_action, run_action
from tools.inputs.manifest import add_manifest_arguments, load_manifest
from tools.staging.project import staged_project


class ProfileError(Exception):
    """The derivation or composition of a runtime profile failed."""


# ==== Composition =============================================================


def compose_profile(detected: Mapping[str, Any], keep: Collection[str]) -> dict[str, Any]:
    """
    Compose the runtime profile from Godot's detection.

    Args:
        detected: The build profile Godot's detection wrote: `disabled_classes` and
            `disabled_build_options`, which holds module switches such as
            `module_openxr_enabled` beside the SCons options.
        keep: Classes the profile never disables, whatever the detection found.

    Returns:
        Godot's profile with the classes of the keep list removed and its classes sorted.
        Its options stay as the editor writes them: a source recipe reads them as its
        Godot version does, leaving out the editor's switches its build lacks.

    Raises:
        ProfileError: The detection lacks a field.
    """
    classes = detected.get("disabled_classes")
    options = detected.get("disabled_build_options")
    if not isinstance(classes, list) or not isinstance(options, dict):
        raise ProfileError(
            "Godot's profile has no disabled_classes and disabled_build_options"
        )
    return {
        "type": "build_profile",
        "disabled_classes": sorted(set(classes) - set(keep)),
        "disabled_build_options": dict(sorted(options.items())),
    }


def render_profile(profile: Mapping[str, Any]) -> str:
    """The `.gdbuild` text: Godot's own layout, sorted keys indented by tabs."""
    return json.dumps(profile, indent="\t", sort_keys=True) + "\n"


# ==== Derivation ==============================================================

# The profile plugin, which the action plugin's staging joins at this resource directory.
_PLUGINS = {"addons/rules_godot_profile": Path(__file__).parent / "profile"}


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
        join_action(root, work, "profile", {"profile": str(detected_path)}, _PLUGINS)
        # The plugin records its result when Godot's detection has finished.
        record = run_action(manifest, execroot, root, work, ["--editor"])
        if not detected_path.is_file():
            raise ProfileError(f"Godot wrote no profile:\n{record['output']}")
        detected = json.loads(detected_path.read_text(encoding="utf-8"))
    profile = compose_profile(detected, manifest["keep_classes"])
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


def place_file(built: Path, target: str, workspace: Path) -> None:
    """
    Write the derived file into the checkout.

    Args:
        built: The derived file.
        target: Its path in the checkout, relative to the workspace.
        workspace: The checkout's root directory.
    """
    destination = workspace / target
    if destination.is_file() and destination.read_bytes() == built.read_bytes():
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(built, destination)
    report(f"wrote {target}; commit it")


def check_file(built: Path, checked_in: Path, target: str, writer: str) -> int:
    """
    Name the checked-in file when it does not match the derivation.

    Args:
        built: The derived file.
        checked_in: The file in the checkout, as the test's runfiles hold it.
        target: Its path in the checkout, relative to the workspace.
        writer: The label whose `bazel run` writes the file.

    Returns:
        1 if the file is stale, else 0.
    """
    derived = built.read_text(encoding="utf-8").splitlines(keepends=True)
    checked = checked_in.read_text(encoding="utf-8").splitlines(keepends=True)
    if derived == checked:
        return 0
    difference = list(
        difflib.unified_diff(checked, derived, "checked in", "derived", n=1)
    )
    more = len(difference) - _DIFF_LINES
    report(
        f"{target} does not match the derivation; write it with bazel run {writer}:\n"
        + "".join(difference[:_DIFF_LINES])
        + (f"... {more} more lines\n" if more > 0 else "")
    )
    return 1


def _check(manifest: dict, runfile: Runfile) -> int:
    checked_in = manifest["checked_in"]
    return check_file(
        runfile(manifest["built"]), runfile(checked_in), checked_in, manifest["writer"]
    )


def _write(manifest: dict, runfile: Runfile, workspace: Path) -> None:
    place_file(runfile(manifest["built"]), manifest["checked_in"], workspace)


def main() -> None:
    if sys.argv[1:2] == ["derive"]:
        _derive(sys.argv[2:])
        return
    sync_main(__doc__ or "", _check, _write, "the runtime profile")


if __name__ == "__main__":
    main()
