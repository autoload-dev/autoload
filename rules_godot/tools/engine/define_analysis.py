"""
Render the macro definition analysis of a source-built engine's C and C++ sources.

Each such source gets a `godot_source_defines` target with its -D and -U options, and its
library compiles with `-include _macros/<library>.h` instead of them. `godot_define_analysis`
targets write those headers, one action per shard: the sources of one directory that the
same runtime variants compile, at most SHARD_SIZE of them. See //godot/engine/private:define_analysis.bzl.
"""

from collections import defaultdict
from collections.abc import Iterable, Mapping
from typing import NamedTuple

try:
    from .build_file import Ref, Rule
except ImportError:
    from build_file import Ref, Rule

# The most sources one analysis action preprocesses. A shard's action runs its sources in
# parallel on one executor, so a large shard lengthens the critical path; a small one
# adds a remote action's overhead per few sources.
SHARD_SIZE = 32

# Top-level directories whose subdirectories are separate libraries; their sources shard
# by subdirectory, so editing one library's headers reruns only its shards.
_NESTED = {"_custom_modules", "drivers", "modules", "platform", "thirdparty"}


class Library(NamedTuple):
    """A source's library, named after it, and the options it compiles with."""

    source: str
    name: str
    copts: Ref
    # None for Objective-C, which keeps its -D options in copts.
    defines: Ref | None
    includes: Ref
    deps: list[str]
    local_defines: list[str]


# The suffixes godot_source_defines takes: C and C++. Assembly sources, though GCC and
# Clang preprocess .S files too, keep their -D options.
ANALYZED_SUFFIXES = (".c", ".cc", ".cpp", ".cxx")


def analyzed(language: str, source: str) -> bool:
    """
    Whether a source takes its definitions from the analysis: C and C++ do.

    Objective-C sources, of the objc language, import implicit modules, which see only the
    command line's macros.
    """
    return language != "objc" and source.endswith(ANALYZED_SUFFIXES)


def is_definition(option: str) -> bool:
    """Whether a compiler option defines or undefines a macro."""
    return option.startswith(("-D", "-U"))


def header(library: str) -> str:
    """The header the analysis writes for a library's source."""
    return f"_macros/{library}.h"


def _defines_target(library: str) -> str:
    return library + "__defines"


def defines_rule(library: Library) -> Rule:
    """The godot_source_defines target of a source, with its library's options."""
    return Rule(
        "godot_source_defines",
        _defines_target(library.name),
        {
            "visibility": ["//visibility:private"],
            "src": library.source,
            "copts": library.copts,
            "defines": library.defines,
            "local_defines": library.local_defines,
            "includes": library.includes,
            "deps": library.deps,
        },
    )


def _directory(source: str) -> str:
    """The directory a source shards by: its top-level one, or below _NESTED the next."""
    parts = source.split("/")[:-1] or ["_root"]
    return "__".join(parts[: 2 if parts[0] in _NESTED else 1])


def _chunks(members: list[Library], size: int) -> list[list[Library]]:
    """
    Split sorted members into the fewest runs of at most size, as even as possible.

    Runs keep neighbouring sources, which tend to share headers, in one shard.
    """
    count = -(-len(members) // size)
    per = -(-len(members) // count)
    return [members[start : start + per] for start in range(0, len(members), per)]


def analysis_rules(
    libraries: Iterable[Library],
    size: int = SHARD_SIZE,
    scopes: Mapping[str, str] | None = None,
) -> list[Rule]:
    """
    The godot_define_analysis targets that write the libraries' headers.

    A shard holds the libraries of one scope and directory. scopes names each library's
    scope, such as the runtime variants that compile it; a library without one is in every
    variant. Compile groups share shards, since each source preprocesses with its own
    options.
    """
    shards: dict[tuple[str, str], list[Library]] = defaultdict(list)
    for library in libraries:
        scope = (scopes or {}).get(library.name, "")
        shards[scope, _directory(library.source)].append(library)
    rules = []
    for (scope, directory), members in sorted(shards.items()):
        chunks = _chunks(sorted(members, key=lambda member: member.source), size)
        for index, chunk in enumerate(chunks):
            suffix = f"__{index}" if len(chunks) > 1 else ""
            rules.append(
                Rule(
                    "godot_define_analysis",
                    f"_macros__{scope}{directory}{suffix}",
                    {
                        "visibility": ["//visibility:private"],
                        "sources": [
                            ":" + _defines_target(member.name) for member in chunk
                        ],
                        "outs": [header(member.name) for member in chunk],
                    },
                    fixed=frozenset({"outs"}),
                )
            )
    return rules
