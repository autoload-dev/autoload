"""
Read and apply a recipe's patches: the files each touches, and strict application.

A recipe owns copies of the files its patches touch, so applying them changes none of the
engine tree's shared files (tree_link.py); the pin action applies them to its own
extraction alike (pin.py).
"""

import re
import shutil
import subprocess
from collections.abc import Sequence
from pathlib import Path
from typing import NamedTuple


class Patches(NamedTuple):
    """A recipe's patch files, applied in order, and the leading path components they strip."""

    files: Sequence[Path] = ()
    strip: int = 1


# The file headers of unified diffs and the extended headers of Git's.
_FILE = re.compile(r"^(?:---|\+\+\+) (.+?)(?:\t.*)?$")
_GIT_FILES = re.compile(r"^diff --git (\S+) (\S+)$")
_GIT_NAME = re.compile(r"^(?:rename|copy) (?:from|to) (.+)$")


def _stripped(name: str, strip: int) -> str | None:
    """A header's file name without its first strip components; None for /dev/null."""
    name = name.strip().strip('"')
    if name == "/dev/null":
        return None
    return "/".join(name.split("/")[strip:]) or None


_HUNK = re.compile(r"^@@ -\d+(?:,(\d+))? \+\d+(?:,(\d+))? @@")


class _Hunk:
    """The lines a hunk has left on its old and new side, which are no file headers."""

    def __init__(self) -> None:
        self.old = self.new = 0

    def consume(self, line: str) -> bool:
        """Whether the line belongs to the current hunk; counts it if so."""
        if self.old <= 0 and self.new <= 0:
            match = _HUNK.match(line)
            if match:
                self.old = int(match[1] if match[1] is not None else 1)
                self.new = int(match[2] if match[2] is not None else 1)
            return bool(match)
        tag = line[:1]
        self.old -= tag in (" ", "", "-")
        self.new -= tag in (" ", "", "+")
        return True


def touched(text: str, strip: int) -> set[str]:
    """
    Return the files a patch changes, adds, deletes, renames, copies or changes the mode of.

    Lines inside a hunk are content, even where they look like file headers.
    """
    names: set[str] = set()
    hunk = _Hunk()
    for line in text.splitlines():
        if hunk.consume(line):
            continue
        if match := _FILE.match(line):
            names.add(_stripped(match[1], strip) or "")
        elif match := _GIT_FILES.match(line):
            names.update(_stripped(name, strip) or "" for name in match.groups())
        elif match := _GIT_NAME.match(line):
            names.add(match[1].strip().strip('"'))
    names.discard("")
    return names


def apply_patches(root: Path, patches: Sequence[Path | str], strip: int) -> None:
    """Apply each patch strictly, with fuzz disabled; a rejected hunk stops the recipe."""
    if patches and not shutil.which("patch"):
        raise SystemExit("Applying source patches requires the patch command on PATH")
    for patch in patches:
        result = subprocess.run(
            ["patch", f"-p{strip}", "-F0", "-t", "-N", "-i", str(Path(patch).resolve())],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode:
            raise SystemExit(
                f"Error applying patch {patch} (strict matching, fuzz disabled):\n"
                f"{result.stdout}{result.stderr}"
            )
