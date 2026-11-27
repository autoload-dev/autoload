"""Write Godot source files and patches of them for the engine tool tests."""

from pathlib import Path


def write_tree(root: Path, files: dict[str, str]) -> None:
    """Write files below a source root."""
    for name, text in files.items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text(text)


def git_patch(*files: tuple[str, str, str]) -> str:
    """A unified diff of (old name, new name, hunks) entries, as git writes it."""
    return "".join(
        f"diff --git a/{old} b/{new}\n--- {'a/' + old if old else '/dev/null'}\n"
        f"+++ {'b/' + new if new else '/dev/null'}\n{hunks}"
        for old, new, hunks in files
    )


# class_db.h's include of the build profile, as upstream writes it.
UPSTREAM_CLASS_DB = (
    "#pragma once\n"
    "#define GD_IS_CLASS_ENABLED(m_class) is_class_enabled_v<m_class>\n\n"
    '#include "core/disabled_classes.gen.h" // IWYU pragma: keep.\n'
    "#define GDREGISTER_CLASS(m_class) if constexpr (GD_IS_CLASS_ENABLED(m_class)) {}\n"
)
