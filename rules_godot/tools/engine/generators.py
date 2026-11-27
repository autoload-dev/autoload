"""
Render the source generators of a configured engine graph: one rule per upstream generator.

Each generator's specification is a file named by its content, and its rule is named after
its first output, so the runtime variants of a recipe, which share one package, declare a
generator they share once.
"""

from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

from tools.engine.build_file import Rule
from tools.engine.include_graph import Generated
from tools.engine.source_tree import SOURCE_SUFFIXES, digest_of


def spec_path(spec: Mapping[str, Any]) -> str:
    """
    The file of a generator's specification, named by its content.

    The runtime variants of a recipe share one package, where a generator whose
    specification differs between them takes one file per specification.
    """
    return f"_bazel_generators/{digest_of(spec)[:16]}.json"


def generator_name(spec: Mapping[str, Any]) -> str:
    """A generator's target, named after its first output, the same in every variant."""
    return "_generate__" + spec["targets"][0].replace("/", "__")


# The attributes of a generator that Bazel cannot select: its declared outputs and the
# switch its macro reads.
_FIXED = frozenset({"outs", "class_profile"})


def generator_rule(
    spec: Mapping[str, Any],
    inputs: Mapping[str, str],
    registered: bool = False,
) -> Rule:
    """
    Return one generator's rule.

    The generator of core/disabled_classes.gen.h reads the class list of the application's
    build profile, which godot_app's build_profile selects, when it runs, so a profile's
    classes need no pin. In a runtime variant's graph the
    application's profile is a registered runtime profile, which may set build options.
    """
    attributes: dict[str, object] = {
        "spec": spec_path(spec),
        "inputs": dict(inputs),
        "outs": spec["targets"],
    }
    if spec["function"] == "disabled_class_builder":
        attributes["class_profile"] = True
        if registered:
            attributes["registered_profile"] = True
    return Rule("godot_source_generator", generator_name(spec), attributes, _FIXED)


def generator_rules(
    generators: Sequence[tuple[dict[str, Any], set[str]]],
    python_files: Sequence[str],
    registered: bool = False,
) -> tuple[list[Rule], list[str]]:
    """
    Return each generator's rule and its generated headers.

    A generator's inputs are its dependencies and the Python files of the source tree.
    """
    rules: list[Rule] = []
    generated_headers: list[str] = []
    for spec, dependencies in generators:
        inputs = {source: source for source in sorted(dependencies | set(python_files))}
        # A script's SCsub is needed for inspection provenance, but its captured
        # function is executed alone by tools/engine/generator.py.
        inputs[spec["code_file"]] = spec["code_file"]
        rules.append(generator_rule(spec, inputs, registered))
        generated_headers.extend(
            name for name in spec["targets"] if Path(name).suffix not in SOURCE_SUFFIXES
        )
    return rules, generated_headers


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
