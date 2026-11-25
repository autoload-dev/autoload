"""
Give a source-built engine's build profile only to the sources that register classes.

Godot's build profile disables classes through core/disabled_classes.gen.h, which
core/object/class_db.h includes, so nearly every source would depend on it, and changing
the profile would recompile them all. Only class registration evaluates it, through
GD_IS_CLASS_ENABLED and the GDREGISTER_* macros. Rendering therefore lets class_db.h
include the profile only where GODOT_DECLARES_BUILD_PROFILE is defined, and defines it
for the sources that can reach a registration. Elsewhere GD_IS_CLASS_ENABLED names an
undeclared identifier, so a source the scan misses fails to compile instead of
registering a disabled class.
"""

import re
from collections.abc import Callable, Collection, Mapping
from pathlib import Path

try:
    from .include_graph import Generated, components
except ImportError:
    from include_graph import Generated, components

HEADER = "core/disabled_classes.gen.h"
DEFINE = "GODOT_DECLARES_BUILD_PROFILE"
_CLASS_DB = "core/object/class_db.h"

_UPSTREAM = """\
#define GD_IS_CLASS_ENABLED(m_class) is_class_enabled_v<m_class>

#include "core/disabled_classes.gen.h" // IWYU pragma: keep.
"""

_SCOPED = f"""\
// rules_godot gives the build profile only to the sources that register classes, so a
// profile change recompiles those alone (tools/engine/build_profile.py).
#ifdef {DEFINE}
#define GD_IS_CLASS_ENABLED(m_class) is_class_enabled_v<m_class>
#include "core/disabled_classes.gen.h" // IWYU pragma: keep.
#else
#define GD_IS_CLASS_ENABLED(m_class) GODOT_BUILD_PROFILE_NOT_DECLARED_FOR_##m_class
#endif
"""

# What evaluates the profile, outside class_db.h, which defines it: the registration
# macros, and the trait itself, whose primary template would silently count a disabled
# class as enabled. A specialization, such as the profile's own, evaluates nothing, and
# ClassDB::is_class_enabled(), a call, asks the registered classes.
_REGISTRATION = re.compile(
    r"\bGDREGISTER_\w+|\bGD_IS_CLASS_ENABLED\b"
    r"|\bis_class_enabled_v\b|(?<!struct )\bis_class_enabled[ \t]*<"
)


def scope(root: Path) -> bool:
    """
    Rewrite class_db.h to include the build profile only where it is declared.

    Return whether the tree has upstream's include, which a fork may have changed; then
    every source keeps the profile.
    """
    path = root / _CLASS_DB
    text = path.read_text() if path.is_file() else ""
    if text.count(_SCOPED) == 1:
        # Scoped already, for another runtime variant of the recipe.
        return True
    if text.count(_UPSTREAM) != 1:
        return False
    path.write_text(text.replace(_UPSTREAM, _SCOPED))
    return True


def _registers(root: Path, name: str, generated: Mapping[str, Generated]) -> bool:
    if name == _CLASS_DB:
        return False
    if name in generated:
        return bool(_REGISTRATION.search(generated[name].code))
    path = root / name
    return path.is_file() and bool(_REGISTRATION.search(path.read_text(errors="replace")))


def _reaching(
    graph: Mapping[str, Collection[str]], matches: Callable[[str], bool]
) -> set[str]:
    """Return the files whose include closure, themselves included, has a matching file."""
    found: set[str] = set()
    for component in components(graph):
        # What a component includes decides before its files are read.
        reaches = any(
            include in found for name in component for include in graph[name]
        ) or any(matches(name) for name in component)
        if reaches:
            found.update(component)
    return found


def declare(
    root: Path,
    graph: Mapping[str, Collection[str]],
    generated: Mapping[str, Generated],
    sources: Collection[str],
) -> tuple[dict[str, frozenset[str]], set[str]]:
    """
    Return the include graph with the profile only for registering sources, and those sources.

    class_db.h no longer reaches the profile; a source that can reach a registration
    includes it directly.
    """
    graph = {name: frozenset(includes) for name, includes in graph.items()}
    if _CLASS_DB in graph:
        graph[_CLASS_DB] -= {HEADER}
    registering = _reaching(graph, lambda name: _registers(root, name, generated))
    users = registering.intersection(sources)
    for source in users:
        graph[source] = graph[source] | {HEADER}
    return graph, users
