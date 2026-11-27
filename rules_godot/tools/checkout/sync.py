"""The runner of a checkout writer: `bazel run` writes files into the checkout, its test checks them."""

import argparse
import json
import os
from collections.abc import Callable
from pathlib import Path

from tools.inputs.runfiles import report, runfile_locator

# Resolves a Bazel short path of the runfiles to the file.
Runfile = Callable[[str], Path]


def sync_main(
    description: str,
    check: Callable[[dict, Runfile], int],
    write: Callable[[dict, Runfile, Path], None],
    noun: str,
) -> None:
    """
    Read the launcher's manifest and check or write, as its `test` field says.

    Args:
        description: The runner's description for --help.
        check: Compares the checkout with what the build derived, reporting each
            difference, and returns the exit status; the test's run.
        write: Writes what the build derived into the workspace, the given directory;
            the writer's run.
        noun: What the writer writes, for the message of a run outside `bazel run`.

    Raises:
        SystemExit: With the status of the check, or 1 when a write has no workspace.
    """
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("--manifest", required=True, type=Path)
    manifest = json.loads(parser.parse_args().manifest.read_text(encoding="utf-8"))
    runfile = runfile_locator(manifest["workspace"])
    if manifest["test"]:
        raise SystemExit(check(manifest, runfile))
    workspace = os.environ.get("BUILD_WORKSPACE_DIRECTORY")
    if not workspace:
        report(f"write {noun} with bazel run")
        raise SystemExit(1)
    write(manifest, runfile, Path(workspace))
