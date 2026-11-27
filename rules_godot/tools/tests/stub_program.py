"""Executable Python stubs, such as a stand-in for the Godot editor, for the tools' tests."""

import shlex
import sys
from pathlib import Path


def write_stub_program(path: Path, source: str) -> Path:
    """
    Write source as an executable program at path, run by the tests' interpreter.

    A shebang naming the interpreter would exceed Linux's limit on its length in deep
    runfiles trees, so path is a shell script that starts the interpreter on the source
    beside it.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    script = path.with_name(path.name + ".py")
    script.write_text(source, encoding="utf-8")
    path.write_text(
        f'#!/bin/sh\nexec {shlex.quote(sys.executable)} {shlex.quote(str(script))} "$@"\n',
        encoding="utf-8",
    )
    path.chmod(0o755)
    return path
