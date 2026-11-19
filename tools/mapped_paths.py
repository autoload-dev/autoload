"""
Output paths in action manifests, written as path mapping stages them.

A manifest names an output file by its mapped path, bazel-out/cfg/ and the rest of its
path, so that one unit's manifests are the same in every target configuration and its
actions share one cache key. Path mapping stages the action's inputs at those paths.
Without path mapping, as with the flag off, the --root arguments name the output roots of
the files a manifest names, and a mapped path resolves to the root that holds the file.
"""

import argparse
import os
from collections.abc import Callable, Sequence
from typing import Any

MAPPED = "bazel-out/cfg/"


def add_root_arguments(parser: argparse.ArgumentParser) -> None:
    """Add the --root arguments that resolve the mapped paths of a manifest."""
    parser.add_argument(
        "--root",
        dest="roots",
        action="append",
        default=[],
        help="Output root of the action's inputs, such as bazel-out/<configuration>/bin; repeated.",
    )


def resolver(roots: Sequence[str]) -> Callable[[str], str]:
    """Return a function from a manifest's path to the path of the staged file."""
    # bazel-out/<configuration>/ of each root, which a mapped path's rest follows.
    bases = sorted({root.rpartition("/")[0] + "/" for root in roots})

    def resolve(path: str) -> str:
        if not path.startswith(MAPPED) or bases in ([], [MAPPED]):
            return path
        rest = path[len(MAPPED) :]
        if len(bases) == 1:
            return bases[0] + rest
        staged = [base + rest for base in bases if os.path.lexists(base + rest)]
        if len(staged) > 1:
            raise ValueError(f"{path} names a file of several configurations: {staged}")
        return staged[0] if staged else path

    return resolve


def resolve_paths(value: Any, resolve: Callable[[str], str]) -> Any:
    """Resolve every mapped path among the values of a manifest's JSON, keys aside."""
    if isinstance(value, str):
        return resolve(value)
    if isinstance(value, dict):
        return {key: resolve_paths(item, resolve) for key, item in value.items()}
    if isinstance(value, list):
        return [resolve_paths(item, resolve) for item in value]
    return value
