"""
The isolated environment and process group of a Godot process, which editor actions and
source runs start.
"""

import os
import signal
import subprocess
from pathlib import Path

# Godot runs in its own process group, so stopping it reaches its descendants.
NEW_SESSION = os.name != "nt"


def stop_process_group(process: subprocess.Popen) -> None:
    """Stop a process started with NEW_SESSION and its descendants, if still running."""
    try:
        if NEW_SESSION:
            os.killpg(process.pid, signal.SIGKILL)
        else:
            process.kill()
    except ProcessLookupError:
        pass


def child_environment(directory: Path) -> dict[str, str]:
    result = {
        k: os.environ[k]
        for k in ("PATH", "SYSTEMROOT", "DEVELOPER_DIR", "SDKROOT")
        if k in os.environ
    }
    for key, leaf in {
        "HOME": "home",
        "TMPDIR": "tmp",
        "XDG_DATA_HOME": "data",
        "XDG_CONFIG_HOME": "config",
        "XDG_CACHE_HOME": "cache",
    }.items():
        path = directory / leaf
        path.mkdir(parents=True, exist_ok=True)
        result[key] = str(path)
    result.update(
        LANG="en_US.UTF-8",
        LC_ALL="en_US.UTF-8",
        TZ="UTC",
        GODOT_SILENCE_ROOT_WARNING="1",
    )
    return result
