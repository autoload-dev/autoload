"""
Render the macro definition analysis of a source-built engine's C and C++ sources.

Each such source gets a `godot_source_defines` target with its -D and -U options, and its
library compiles with `-include _macros/<library>.h` instead of them. `godot_define_analysis`
targets write those headers, one action per shard: the sources of one compile group and
directory, at most SHARD_SIZE of them. See //godot/engine/private:define_analysis.bzl.
"""

from collections import defaultdict
from collections.abc import Iterable, Sequence
from typing import NamedTuple

# The most sources one analysis action preprocesses. A shard's action runs its sources in
# parallel on one executor, so a large shard lengthens the critical path; a small one
# adds a remote action's overhead per few sources.
SHARD_SIZE = 32

# Top-level directories whose subdirectories are separate libraries; their sources shard
# by subdirectory, so editing one library's headers reruns only its shards.
_NESTED = {"_custom_modules", "drivers", "modules", "platform", "thirdparty"}


class AnalyzedSource(NamedTuple):
    """A source whose library takes its macro definitions from the analysis."""

    group: int
    source: str
    library: str


def is_definition(option: str) -> bool:
    """Whether a compiler option defines or undefines a macro."""
    return option.startswith(("-D", "-U"))


def header(library: str) -> str:
    """The header the analysis writes for a library's source."""
    return f"_macros/{library}.h"


def defines_rule(
    analyzed: AnalyzedSource,
    includes: str,
    local_defines: Sequence[str],
    deps: Sequence[str],
) -> str:
    """The godot_source_defines target of a source, with its library's options."""
    return (
        f"godot_source_defines(name = {_defines_target(analyzed.library)!r}, "
        f"visibility = ['//visibility:private'], src = {analyzed.source!r}, "
        f"copts = _COPTS_{analyzed.group}, defines = _DEFINES_{analyzed.group}, "
        f"local_defines = {list(local_defines)!r}, includes = {includes}, deps = {list(deps)!r})"
    )


def analysis_rules(
    sources: Iterable[AnalyzedSource], size: int = SHARD_SIZE
) -> list[str]:
    """The godot_define_analysis targets that write the sources' headers."""
    shards: dict[tuple[int, str], list[AnalyzedSource]] = defaultdict(list)
    for analyzed in sources:
        shards[analyzed.group, _directory(analyzed.source)].append(analyzed)
    lines = []
    for (group, directory), members in sorted(shards.items()):
        chunks = _chunks(sorted(members, key=lambda member: member.source), size)
        for index, chunk in enumerate(chunks):
            name = f"_macros__{group}__{directory}" + (
                f"__{index}" if len(chunks) > 1 else ""
            )
            lines.append(
                f"godot_define_analysis(name = {name!r}, visibility = ['//visibility:private'], "
                f"sources = {[':' + _defines_target(member.library) for member in chunk]!r}, "
                f"outs = {[header(member.library) for member in chunk]!r})"
            )
    return lines


def _defines_target(library: str) -> str:
    return library + "__defines"


def _directory(source: str) -> str:
    """The directory a source shards by: its top-level one, or below _NESTED the next."""
    parts = source.split("/")[:-1] or ["_root"]
    return "__".join(parts[: 2 if parts[0] in _NESTED else 1])


def _chunks(members: list[AnalyzedSource], size: int) -> list[list[AnalyzedSource]]:
    """
    Split sorted members into the fewest runs of at most size, as even as possible.

    Runs keep neighbouring sources, which tend to share headers, in one shard.
    """
    count = -(-len(members) // size)
    per = -(-len(members) // count)
    return [members[start : start + per] for start in range(0, len(members), per)]
