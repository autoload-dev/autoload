"""
Editor actions: the action plugin joined to a staged project, and the editor run whose
record decides the action.
"""

import json
import shutil
import subprocess
import sys
import time
from collections.abc import Mapping
from pathlib import Path

from tools.editor_action.process import NEW_SESSION, child_environment, stop_process_group
from tools.staging.project import configure

# rules_godot's action plugin, staged into every view an editor action runs on.
_ACTION = Path(__file__).parent / "plugin"

ACTION_DIRECTORY = "addons/rules_godot_action"

# Godot's own result of an action, written by the action plugin.
_RECORD = "record.json"

# An editor action's bound, and how long Godot may take to exit after its record.
_ACTION_TIMEOUT_SECONDS = 300

_RECORD_GRACE_SECONDS = 20


def _stage_plugin(root: Path, directory: str, source: Path) -> str:
    """Stage a plugin at a reserved resource directory with a .gdignore; return its plugin.cfg."""
    destination = root / directory
    if destination.exists():
        raise ValueError(f"res://{directory} is reserved for rules_godot")
    shutil.copytree(source, destination)
    (destination / ".gdignore").touch()
    return f"res://{directory}/plugin.cfg"


def join_action(
    root: Path,
    work: Path,
    operation: str,
    parameters: Mapping[str, object] | None = None,
    plugins: Mapping[str, Path] | None = None,
) -> None:
    """
    Stage the action plugin for an operation and enable it in the staged project.

    Its directory holds a .gdignore file, so Godot loads the plugin but never
    scans, imports or exports its files. An export packs the project.godot from
    before the join.

    Args:
        root: The staged project.
        work: The action's work directory, which receives the record.
        operation: What the plugin records, see plugin/plugin.gd.
        parameters: More fields of the plugin's action.json.
        plugins: Plugins of the operation to stage and enable the same way, by the
            resource directory each takes, such as `addons/rules_godot_profile`, and
            the directory it is copied from.

    Raises:
        ValueError: A plugin's resource directory exists in the project.
    """
    enabled = [_stage_plugin(root, ACTION_DIRECTORY, _ACTION)]
    enabled += [
        _stage_plugin(root, name, source) for name, source in (plugins or {}).items()
    ]
    project = root / "project.godot"
    authored = work / "project.godot"
    shutil.copyfile(project, authored)
    (root / ACTION_DIRECTORY / "action.json").write_text(
        json.dumps(
            {
                **(parameters or {}),
                "operation": operation,
                "record": str(work / _RECORD),
                "project_file": str(authored),
            }
        ),
        encoding="utf-8",
    )
    configure(root, enabled, {})


def _status(returncode: int) -> str:
    return f"signal {-returncode}" if returncode < 0 else f"exit status {returncode}"


def _await_record(
    process: subprocess.Popen[bytes], record: Path, log: Path, operation: str
) -> bool:
    """
    Wait for Godot's record, then a grace period for Godot to exit.

    Returns:
        Whether Godot was still running after the grace period and is to be stopped.
    """
    deadline = time.monotonic() + _ACTION_TIMEOUT_SECONDS
    while not record.exists() and process.poll() is None:
        if time.monotonic() > deadline:
            stop_process_group(process)
            process.wait()
            raise RuntimeError(
                f"Godot recorded no {operation} result within "
                f"{_ACTION_TIMEOUT_SECONDS} seconds:\n"
                + log.read_text(encoding="utf-8", errors="replace")
            )
        time.sleep(0.05)
    if not record.exists():
        return False
    try:
        process.wait(timeout=_RECORD_GRACE_SECONDS)
    except subprocess.TimeoutExpired:
        return True
    return False


def _successful_record(
    record: Path, output: str, operation: str, returncode: int
) -> dict:
    """The action plugin's record; fail when Godot wrote none or a failed one."""
    if not record.exists():
        raise RuntimeError(
            f"Godot ended without recording its {operation} result "
            f"({_status(returncode)}):\n{output}"
        )
    result = json.loads(record.read_text(encoding="utf-8"))
    if result["verdict"] != "success":
        raise RuntimeError(
            f"Godot recorded a failed {operation}:\n"
            + "\n".join(result["diagnostics"])
            + f"\nGodot's output:\n{output}"
        )
    return result


def _note_ending(stopped: bool, returncode: int, operation: str) -> None:
    """Note a Godot that was stopped or failed after a successful record."""
    if stopped:
        print(
            f"rules_godot: note: stopped Godot {_RECORD_GRACE_SECONDS} seconds "
            f"after its {operation} result",
            file=sys.stderr,
        )
    elif returncode:
        print(
            f"rules_godot: note: Godot ended with {_status(returncode)} "
            f"after a successful {operation}",
            file=sys.stderr,
        )


def run_action(
    manifest: dict, execroot: Path, root: Path, work: Path, args: list[str]
) -> dict:
    """
    Run the manifest's editor on the staged project; return the action's record.

    The record the action plugin writes decides, not Godot's output or exit
    status: Godot is stopped a grace period after its record, and an exit
    after a successful record is only a note. The caller checks the action's
    declared outputs.
    """
    operation = json.loads(
        (root / ACTION_DIRECTORY / "action.json").read_text(encoding="utf-8")
    )["operation"]
    record = work / _RECORD
    record.unlink(missing_ok=True)
    log = work / "godot.out"
    command = [
        str((execroot / manifest["editor"]).resolve()),
        "--headless",
        "--path",
        str(root),
        "--log-file",
        str(work / "godot.log"),
        *args,
    ]
    with log.open("wb") as sink:
        process = subprocess.Popen(
            command,
            cwd=root,
            env=child_environment(work),
            stdout=sink,
            stderr=subprocess.STDOUT,
            start_new_session=NEW_SESSION,
        )
        try:
            stopped = _await_record(process, record, log, operation)
        finally:
            stop_process_group(process)
            process.wait()
    output = log.read_text(encoding="utf-8", errors="replace")
    result = _successful_record(record, output, operation, process.returncode)
    result["output"] = output
    result["stopped"] = stopped
    _note_ending(stopped, process.returncode, operation)
    return result
