"""Run a Linux or macOS application on this host with its log on the terminal."""

from __future__ import annotations

import os
import shutil
import tempfile
from collections.abc import Callable, Mapping
from typing import Any

import launch_common

OPTIONS = frozenset({"headless", "fresh", "detach", "env"})

# Godot keeps user:// and its settings below these; --fresh points them at an empty
# directory. On macOS Godot reads HOME for ~/Library/Application Support.
_DATA_VARIABLES = ("HOME", "XDG_DATA_HOME", "XDG_CONFIG_HOME", "XDG_CACHE_HOME")


def launch(
    manifest: Mapping[str, Any],
    options: launch_common.Options,
    runfile: Callable[[str], str],
) -> int:
    command = [runfile(manifest["executable"])]
    if options.headless:
        command.append("--headless")
    command.extend(options.godot_args)
    env = dict(os.environ) | dict(options.env)
    fresh = tempfile.mkdtemp(prefix="rules_godot_fresh_") if options.fresh else None
    if fresh:
        launch_common.log(f"--fresh: user data in {fresh}")
        env |= {name: fresh for name in _DATA_VARIABLES}
    try:
        return launch_common.run_on_host(command, env, detach=options.detach)
    finally:
        # A detached application keeps its user data until it exits.
        if fresh and not options.detach:
            shutil.rmtree(fresh, ignore_errors=True)
