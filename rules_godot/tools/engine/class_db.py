"""
Scope the build profile in a recipe's class_db.h.

Upstream's class_db.h includes the build profile, so nearly every source would depend on
it. A recipe's copy includes it only where GODOT_DECLARES_BUILD_PROFILE is defined;
build_profile.py defines it for the sources that can reach a registration. The recipe
scopes its own copy after its patches, so a fork's patch of class_db.h applies to
upstream's text and the engine tree stays the archive's.
"""

from pathlib import Path

HEADER = "core/disabled_classes.gen.h"
DEFINE = "GODOT_DECLARES_BUILD_PROFILE"
CLASS_DB = "core/object/class_db.h"

_UPSTREAM = f"""\
#define GD_IS_CLASS_ENABLED(m_class) is_class_enabled_v<m_class>

#include "{HEADER}" // IWYU pragma: keep.
"""

_SCOPED = f"""\
// rules_godot gives the build profile only to the sources that register classes, so a
// profile change recompiles those alone (tools/engine/build_profile.py).
#ifdef {DEFINE}
#define GD_IS_CLASS_ENABLED(m_class) is_class_enabled_v<m_class>
#include "{HEADER}" // IWYU pragma: keep.
#else
#define GD_IS_CLASS_ENABLED(m_class) GODOT_BUILD_PROFILE_NOT_DECLARED_FOR_##m_class
#endif
"""


def scope(root: Path) -> None:
    """Rewrite upstream's class_db.h to include the build profile only where it is declared."""
    path = root / CLASS_DB
    text = path.read_text() if path.is_file() else ""
    if text.count(_UPSTREAM) == 1:
        path.write_text(text.replace(_UPSTREAM, _SCOPED))


def is_scoped(root: Path) -> bool:
    """
    Return whether the recipe's class_db.h includes the build profile only where declared.

    A fork that changed upstream's include keeps it, and every source the profile.
    """
    path = root / CLASS_DB
    return path.is_file() and path.read_text().count(_SCOPED) == 1
