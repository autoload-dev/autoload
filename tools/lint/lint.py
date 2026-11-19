"""Run the pinned Ruff linter and ty type checker over the workspace."""

import os
import subprocess
import sys
from pathlib import Path


def main() -> int:
    ruff, ty = (Path(path).resolve() for path in sys.argv[1:3])
    root = os.environ["BUILD_WORKSPACE_DIRECTORY"]
    status = 0
    for command in ([ruff, "check", *sys.argv[3:]], [ty, "check"]):
        status |= subprocess.run(command, cwd=root, check=False).returncode
    return status


if __name__ == "__main__":
    sys.exit(main())
