"""Identify file contents by digest without loading them into memory."""

import hashlib
from pathlib import Path


def digest(path: Path) -> str:
    """Return the SHA-256 of a file, as hex."""
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()
