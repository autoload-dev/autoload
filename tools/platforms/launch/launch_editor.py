"""
Run an application's project from sources with Godot's editor binary on this host.

godot_run's runner, tools/godot_run.py, stages the project from its run manifest and
runs Godot; this module starts it with the options every application backend shares.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Mapping
from typing import Any

import launch_common
from launch_common import LaunchError

OPTIONS = frozenset({"headless", "detach", "env"})

# Godot options that would replace what the runner controls: the project, what runs
# and the editor instead of the game.
_CONTROLLED = frozenset(
    {
        "--path",
        "--upwards",
        "--main-pack",
        "-e",
        "--editor",
        "-p",
        "--project-manager",
        "-s",
        "--script",
    }
)


def launch(
    manifest: Mapping[str, Any],
    options: launch_common.Options,
    runfile: Callable[[str], str],
) -> int:
    controlled = sorted(set(options.godot_args) & _CONTROLLED)
    if controlled:
        raise LaunchError(
            f"{', '.join(controlled)} would replace the project the editor variant runs"
        )
    # The runner isolates Godot's environment; --env pairs before its manifest add to it.
    command = [runfile(manifest["runner"])]
    for name, value in options.env.items():
        command += ["--env", f"{name}={value}"]
    command += ["--manifest", runfile(manifest["manifest"])]
    if options.headless:
        command.append("--headless")
    command.extend(options.godot_args)
    return launch_common.run_on_host(command, dict(os.environ), detach=options.detach)
