"""
Render the source generators of a configured engine graph: one rule per upstream generator.

Each generator's specification is a file named by its content, and its rule is named after
its first output, so the runtime variants of a recipe, which share one package, declare a
generator they share once.
"""

import argparse
import hashlib
import json
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

try:
    from .include_graph import Generated
    from .source_tree import SOURCE_SUFFIXES, relative
except ImportError:
    from include_graph import Generated
    from source_tree import SOURCE_SUFFIXES, relative


def multiline_rule(rule: str, attributes: Mapping[str, object]) -> str:
    return (
        rule
        + "(\n"
        + "".join(f"    {key} = {value!r},\n" for key, value in attributes.items())
        + ")"
    )


def spec_path(spec: Mapping[str, Any]) -> str:
    """
    The file of a generator's specification, named by its content.

    The runtime variants of a recipe share one package, where a generator whose
    specification differs between them takes one file per specification.
    """
    content = json.dumps(spec, sort_keys=True).encode()
    return f"_bazel_generators/{hashlib.sha256(content).hexdigest()[:16]}.json"


def generator_name(spec: Mapping[str, Any]) -> str:
    """A generator's target, named after its first output, the same in every variant."""
    return "_generate__" + spec["targets"][0].replace("/", "__")


def generator_attributes(
    name: str,
    spec: Mapping[str, Any],
    inputs: Mapping[str, str],
    args: argparse.Namespace,
) -> dict[str, object]:
    """
    Return the attributes of one generator's rule.

    The generator of core/disabled_classes.gen.h reads the class list of a build profile when
    it runs: the application's, which godot_app's build_profile selects, or else the
    recipe's own, so a profile's classes need no pin. An application's profile may set
    build options only if it is one of the engine's registered runtime profiles.
    """
    attributes: dict[str, object] = {
        "name": name,
        "spec": spec_path(spec),
        "inputs": dict(inputs),
        "outs": spec["targets"],
    }
    if spec["function"] == "disabled_class_builder":
        attributes["class_profile"] = True
        if args.recipe_profile:
            attributes["recipe_profile"] = args.recipe_profile
        attributes["runtime_profiles"] = list(args.runtime_profiles)
        if args.engine:
            attributes["engine"] = args.engine
    return attributes


def generator_rules(
    args: argparse.Namespace,
    root: Path,
    generators: Sequence[tuple[dict[str, Any], set[str]]],
) -> tuple[list[str], list[str]]:
    """
    Return each generator's rule and its generated headers.

    A generator's inputs are its dependencies and the Python files of the source tree.
    """
    python_files = sorted(
        relative(path, root)
        for path in root.rglob("*.py")
        if "_scons" not in path.parts and "_bazel_generators" not in path.parts
    )
    lines: list[str] = []
    generated_headers: list[str] = []
    for spec, dependencies in generators:
        inputs = {source: source for source in sorted(dependencies | set(python_files))}
        # A script's SCsub is needed for inspection provenance, but its captured
        # function is executed alone by tools/engine/generator.py.
        inputs[spec["code_file"]] = spec["code_file"]
        attributes = generator_attributes(generator_name(spec), spec, inputs, args)
        lines.append(multiline_rule("godot_source_generator", attributes))
        generated_headers.extend(
            name for name in spec["targets"] if Path(name).suffix not in SOURCE_SUFFIXES
        )
    return lines, generated_headers


def generated_files(
    root: Path, specs: Iterable[Mapping[str, Any]]
) -> dict[str, Generated]:
    """Return each generated file with its generator's code, inputs and outputs."""
    files: dict[str, Generated] = {}
    for spec in specs:
        code = spec.get("inline") or (root / spec["code_file"]).read_text()
        inputs = tuple(entry["path"] for entry in spec["sources"] if "path" in entry)
        outputs = tuple(spec["targets"])
        files.update((target, Generated(code, inputs, outputs)) for target in outputs)
    return files
