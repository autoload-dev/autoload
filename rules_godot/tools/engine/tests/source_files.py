"""Write Godot source files below a temporary root for the engine tool tests."""

from pathlib import Path


def write_tree(root: Path, files: dict[str, str]) -> None:
    """Write files below a source root."""
    for name, text in files.items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text(text)
