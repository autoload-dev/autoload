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
from collections.abc import Collection, Iterable, Mapping
from pathlib import Path, PurePosixPath
from typing import Any

from tools.engine.class_db import CLASS_DB as _CLASS_DB
from tools.engine.class_db import HEADER
from tools.engine.custom_modules import DIRECTORY
from tools.engine.include_graph import ANY_HEADER, Generated, reaching
from tools.engine.source_tree import SOURCE_SUFFIXES

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


def _is_code_source(name: str) -> bool:
    """Whether a file is a custom module's source, whose text comes by label at build time."""
    path = PurePosixPath(name)
    return path.parts[0] == DIRECTORY and path.suffix in SOURCE_SUFFIXES


def declare(
    root: Path,
    graph: Mapping[str, Collection[str]],
    generated: Mapping[str, Generated],
    sources: Collection[str],
) -> tuple[dict[str, frozenset[str]], set[str]]:
    """
    Return the include graph with the profile only for registering sources, and those sources.

    class_db.h no longer reaches the profile; a source that can reach a registration
    includes it directly. A custom module's code sources, whose text comes by label at
    build time, count as registering. Its headers declare, as Godot's do, and ANY_HEADER,
    which stands for every header a source reaching them may include, registers nothing:
    those engine sources keep their configuration, and a header that registers anyway
    fails their compilation instead of registering a disabled class.
    """
    graph = {name: frozenset(includes) for name, includes in graph.items()}
    for name in [_CLASS_DB, ANY_HEADER]:
        if name in graph:
            graph[name] -= {HEADER}
    view = {name: includes - {ANY_HEADER} for name, includes in graph.items()}
    registering = reaching(
        view, lambda name: _is_code_source(name) or _registers(root, name, generated)
    )
    users = registering.intersection(sources)
    for source in users:
        graph[source] = graph[source] | {HEADER}
    return graph, users
