"""
The command line of //tools/project:project_config: compose a purpose's project.godot, list the
settings a view's members leave out, check that no override hides a flag's setting, and list
a project's autoloads, each as the rules' actions run it.
"""

import argparse
import json
import sys
from pathlib import Path

from tools.project.config import (
    authored_autoloads,
    compose_project,
    left_out,
    override_applies,
    shadowed,
)


def _compose(arguments: list[str]) -> None:
    parser = argparse.ArgumentParser(description="Construct a purpose's project.godot.")
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(arguments)
    data = json.loads(args.manifest.read_text(encoding="utf-8"))
    features = data.get("features")
    active_features = (
        {tag for tag, active in json.loads(Path(features).read_text()).items() if active}
        if features
        else None
    )
    base = Path(data["project_file"]).read_text(encoding="utf-8")
    excluded = (
        [setting for setting, _ in json.loads(Path(data["left_out"]).read_text())]
        if "left_out" in data
        else []
    )
    result = compose_project(
        base,
        data.get("settings", {}),
        data.get("autoloads", {}),
        data.get("main_scene", ""),
        purpose=data.get("purpose", "runtime"),
        editor_plugins=data.get("editor_plugins", []),
        active_features=active_features,
        kinds=data.get("kinds"),
        sections=data.get("sections"),
        excluded=excluded,
        context_only=data.get("context_only", False),
        pinned=data.get("pinned_settings"),
    )
    args.output.write_text(result, encoding="utf-8")


def _left_out(arguments: list[str]) -> None:
    parser = argparse.ArgumentParser(
        description="List the authored content-bound settings a view's members leave out."
    )
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(arguments)
    data = json.loads(args.manifest.read_text(encoding="utf-8"))
    base = Path(data["project_file"]).read_text(encoding="utf-8")
    entries = left_out(base, data["kinds"], data["members"])
    # A program entry starts the game itself, so it needs every file its configuration
    # names, except those of overrides whose tags it never has.
    program_entry = data.get("program_entry")
    features = data.get("features")
    needed = [entry for entry in entries if override_applies(entry[0], features)]
    if program_entry and needed:
        sys.exit(
            "".join(
                f"{program_entry}: Setting {setting} of the authored project.godot names "
                f"{path}, which is no declared member of its deps\n"
                for setting, path in needed
            ).rstrip()
        )
    args.output.write_text(json.dumps(entries), encoding="utf-8")


def _shadowed(arguments: list[str]) -> None:
    parser = argparse.ArgumentParser(
        description="Check that no authored feature override hides a setting from a flag."
    )
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(arguments)
    data = json.loads(args.manifest.read_text(encoding="utf-8"))
    base = Path(data["project_file"]).read_text(encoding="utf-8")
    conflicts = shadowed(base, data["flag_keys"])
    if conflicts:
        sys.exit("\n".join(conflicts))
    args.output.write_text("", encoding="utf-8")


def _autoloads(arguments: list[str]) -> None:
    parser = argparse.ArgumentParser(
        description="List the autoloads of an authored project.godot as JSON."
    )
    parser.add_argument("--project-file", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(arguments)
    autoloads = authored_autoloads(args.project_file.read_text(encoding="utf-8"))
    args.output.write_text(json.dumps(autoloads, indent=1) + "\n", encoding="utf-8")


def main() -> None:
    commands = {
        "compose": _compose,
        "left-out": _left_out,
        "shadowed": _shadowed,
        "autoloads": _autoloads,
    }
    if sys.argv[1:2] and sys.argv[1] in commands:
        commands[sys.argv[1]](sys.argv[2:])
        return
    sys.exit(
        "usage: project_config compose|left-out|shadowed --manifest FILE --output FILE\n"
        "       project_config autoloads --project-file FILE --output FILE"
    )


if __name__ == "__main__":
    main()
