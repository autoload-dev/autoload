"""
Read build profiles, and give a source-built engine's profile only to the sources that
register classes.

Godot's build profile disables classes through core/disabled_classes.gen.h, which
core/object/class_db.h includes, so nearly every source would depend on it, and changing
the profile would recompile them all. Only class registration evaluates it, through
GD_IS_CLASS_ENABLED and the GDREGISTER_* macros. A recipe's class_db.h therefore
includes the profile only where GODOT_DECLARES_BUILD_PROFILE is defined (class_db.py),
and rendering defines it for the sources that can reach a registration. Elsewhere
GD_IS_CLASS_ENABLED names an undeclared identifier, so a source the scan misses fails to compile instead of
registering a disabled class.

Sections: Profile files, Scoping.
"""

import json
import re
from collections.abc import Callable, Collection, Iterable, Mapping
from pathlib import Path
from typing import Any

try:
    from .class_db import CLASS_DB as _CLASS_DB
    from .class_db import HEADER
    from .include_graph import Generated, components
except ImportError:
    from class_db import CLASS_DB as _CLASS_DB
    from class_db import HEADER
    from include_graph import Generated, components

# ==== Profile files ===========================================================


def read_profile(profile: Path) -> dict[str, Any]:
    """Return a build profile's JSON object."""
    try:
        data = json.loads(profile.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"The build profile is not readable JSON: {error}") from error
    if not isinstance(data, dict):
        raise TypeError("The build profile must be a JSON object")
    return data


def build_options(profile: Mapping[str, Any]) -> dict[str, Any]:
    """
    Return a build profile's build options, the part that shapes a recipe's graph.

    Its class list reaches the engine as an action input instead: the generator of
    core/disabled_classes.gen.h reads it when it runs.
    """
    return dict(profile.get("disabled_build_options") or {})


def class_list_spec(
    spec: Mapping[str, Any], classes: Iterable[str] = ()
) -> dict[str, Any]:
    """
    Return a generator specification with the given class list of a build profile.

    Only the class generator's changes. A pinned graph holds no class list, so it stays
    valid whatever classes the recipe's or an application's profile disables.
    """
    if spec["function"] != "disabled_class_builder":
        return dict(spec)
    return dict(spec) | {"sources": [{"value": list(classes)}]}


# ==== Scoping =================================================================

# What evaluates the profile, outside class_db.h, which defines it: the registration
# macros, and the trait itself, whose primary template would silently count a disabled
# class as enabled. A specialization, such as the profile's own, evaluates nothing, and
# ClassDB::is_class_enabled(), a call, asks the registered classes.
_REGISTRATION = re.compile(
    r"\bGDREGISTER_\w+|\bGD_IS_CLASS_ENABLED\b"
    r"|\bis_class_enabled_v\b|(?<!struct )\bis_class_enabled[ \t]*<"
)


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
