"""
Write the lock file of an engine's recipe pins: all of them, or some merged into it.

Recipes of one build target share their generators whatever the platform or CPU, so the
lock stores each distinct generator list once, by its digest. A recipe's runtime variants
pin in the lock's variants table, by recipe and runtime profile.
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any

try:
    from . import configure
except ImportError:
    # Run as a binary, the tool imports its sibling modules from its own directory.
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import configure  # type: ignore[no-redef]


def _write(
    path: Path,
    generators: dict[str, Any],
    recipes: dict[str, Any],
    variants: dict[str, dict[str, Any]],
) -> None:
    """
    Write a lock file of recipe pins, their runtime variants' pins and the generator lists
    they refer to; generator lists no pin refers to stay out.
    """
    entries = list(recipes.values()) + [
        pin for pins in variants.values() for pin in pins.values()
    ]
    referenced = {entry["graph"]["generators"] for entry in entries}
    lock: dict[str, object] = {
        "generators": {
            digest: generators[digest]
            for digest in sorted(generators)
            if digest in referenced
        },
        "recipes": dict(sorted(recipes.items())),
    }
    if variants:
        # Each recipe's runtime variants, by the label of their runtime profile.
        lock["variants"] = {
            key: dict(sorted(pins.items())) for key, pins in sorted(variants.items())
        }
    # Only the tables are sorted; one space per level keeps the lock small.
    configure.write_json(path, lock, indent=1)


def merge(arguments: argparse.Namespace) -> None:
    """Write the lock file of every recipe pin and runtime variant pin an engine has."""
    generators: dict[str, Any] = {}

    def stored(path: str) -> dict[str, Any]:
        pin = json.loads(Path(path).read_text())
        shared = pin["graph"]["generators"]
        reference = "sha256:" + configure.digest_of(shared)
        generators[reference] = shared
        pin["graph"]["generators"] = reference
        return pin

    recipes = {}
    for declaration in arguments.recipe:
        key, _, path = declaration.partition("=")
        recipes[key] = stored(path)
    variants: dict[str, dict[str, Any]] = {}
    for key, profile, path in arguments.variant:
        variants.setdefault(key, {})[profile] = stored(path)
    _write(Path(arguments.output), generators, recipes, variants)


def update(lock: Path, partial: Path) -> None:
    """
    Merge a partial lock, the pins of some recipes, into a lock file and keep its other pins.

    Without a lock file, the partial lock becomes it.
    """
    result = configure.read_lock(lock)
    new = json.loads(partial.read_text())
    variants = dict(result.get("variants", {}))
    for key, pins in new.get("variants", {}).items():
        variants[key] = variants.get(key, {}) | pins
    _write(
        lock,
        result.get("generators", {}) | new.get("generators", {}),
        result.get("recipes", {}) | new.get("recipes", {}),
        variants,
    )
