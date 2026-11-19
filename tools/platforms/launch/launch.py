"""
Install and launch a godot_app with `bazel run`, then stream its log until it exits.

The rule writes a manifest naming the platform and the application's runfiles; this
entry point reads it and hands over to the platform's launcher, whose OPTIONS name the
launcher options it accepts. Usage, as the generated wrapper calls it:

    launch.py <manifest> <runfiles directory> [options] [-- <Godot arguments>]
"""

from __future__ import annotations

import importlib
import json
import os
import sys
from collections.abc import Sequence

# Python puts the directory of this file's symlink target first on sys.path; a sandbox
# may stage that target without its siblings, which the runfiles directory holds.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import launch_common


def main(argv: Sequence[str]) -> int:
    manifest_path, runfiles, user_args = argv[0], argv[1], argv[2:]
    with open(manifest_path, encoding="utf-8") as manifest_file:
        manifest = json.load(manifest_file)
    launch_common.interrupt_on_terminate()
    try:
        platform = importlib.import_module("launch_" + manifest["platform"])
        options = launch_common.parse_options(
            user_args, manifest["platform"], platform.OPTIONS
        )
        return platform.launch(
            manifest, options, lambda path: os.path.join(runfiles, path)
        )
    except launch_common.LaunchError as error:
        launch_common.log(f"error: {error}")
        return 2
    except KeyboardInterrupt:
        return launch_common.INTERRUPTED


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
