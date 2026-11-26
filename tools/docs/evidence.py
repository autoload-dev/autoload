"""Evaluated loading and configured facts for the API output-contract checker."""

import json
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from tools.ci.lanes import PROFILE
from tools.conventions.bazel import Bazel
from tools.conventions.context import (
    EvidenceError,
    Module,
    Target,
    query_targets,
    run_tool,
)
from tools.docs.coverage import ModuleInfo, parse_module
from tools.docs.output_contracts import ConfiguredTarget
from tools.setup.modules import RULESET

# Counts and names are all the comparison needs; listing every file is not.
_EVIDENCE = (
    "json.encode({"
    '"label": str(target.label), '
    '"files": len(target.files.to_list()), '
    '"providers": sorted(providers(target).keys()), '
    '"groups": dir(providers(target)["OutputGroupInfo"]) '
    'if "OutputGroupInfo" in providers(target) else [], '
    # A runnable operation has an executable and RunfilesSupport; a single data
    # file can supply an executable pointer without a runfiles manifest.
    '"executable": providers(target)["DefaultInfo"].files_to_run.executable != None '
    'and providers(target)["DefaultInfo"].files_to_run.runfiles_manifest != None, '
    '"runfiles": len(providers(target)["DefaultInfo"].default_runfiles.files.to_list())'
    "})"
)


def unqualified(label: str) -> str:
    """A label without its repository, as cquery and the loading facts are keyed."""
    return label.partition("//")[2]


def decode_configured(output: str) -> dict[str, ConfiguredTarget]:
    """Decode the configured evidence lines of one cquery, keyed by unqualified label."""
    result = {}
    for line in output.splitlines():
        try:
            value = json.loads(line)
            target = ConfiguredTarget(
                label=value["label"],
                files=int(value["files"]),
                runfiles=int(value["runfiles"]),
                executable=bool(value["executable"]),
                providers=frozenset(value["providers"]),
                groups=frozenset(value["groups"]),
            )
        except (ValueError, KeyError, TypeError) as error:
            raise EvidenceError(
                f"invalid evaluated configured evidence: {error}"
            ) from error
        name = unqualified(target.label)
        # A target reached in several configurations, such as a config_setting that a
        # select() reaches in each, is one target while its facts agree.
        if result.get(name, target) != target:
            raise EvidenceError(f"{target.label}: other facts in another configuration")
        result[name] = target
    return result


def invocation(label: str, targets: tuple[Target, ...]) -> tuple[Target, ...]:
    """The rules that the authored call of the root ``label`` emits, among loaded targets."""
    roots = [
        target for target in targets if unqualified(target.label) == unqualified(label)
    ]
    if len(roots) != 1:
        raise EvidenceError(f"{label}: unresolved evaluated invocation root")
    return tuple(target for target in targets if target.origin == roots[0].origin)


# Module paths are relative to the repository root, as the lanes' work names directories:
# the ruleset module, where cases and behavior tests resolve unless they name another module,
# and the repository's root module, which extracts the ruleset's Starlark modules
# (tools/docs/api) and holds the consumer scenarios.
RULESET_MODULE = Module(RULESET, ())
RULESET_DIR = RULESET.as_posix()
DOCS_MODULE = Module(Path("."), ())


class EvaluatedBazel(Bazel):
    """
    Bazel facts for contract fixtures; one instance serves a whole checker run.

    Its root is the repository root, against which module paths resolve. The configured
    queries of its cases run in a Bazel profile, the lane's, so that they keep that
    configuration's analysis apart from the default one of the checker's own build; only
    the root module has profiles (tools/bazel).
    """

    def __init__(self, root: Path, profile: str | None = None) -> None:
        super().__init__(root)
        self.profile = profile

    def run(self, module: Module, *arguments: str, profiled: bool = False) -> str:
        variables = {PROFILE: self.profile} if profiled and self.profile else {}
        return run_tool(
            ["bazel", *arguments, "--noshow_progress"],
            self.root / module.path,
            variables,
        )

    def outputs(
        self, targets: Iterable[str], module: Module = RULESET_MODULE
    ) -> dict[str, Path]:
        """Build file targets of a module and return their output paths."""
        targets = sorted(targets)
        self.run(module, "build", *targets)
        paths = self.run(
            module, "cquery", "set(" + " ".join(targets) + ")", "--output=files"
        ).split()
        result = {}
        for target in targets:
            suffix = unqualified(target).replace(":", "/")
            matches = [path for path in paths if path.endswith(suffix)]
            if len(matches) != 1:
                raise EvidenceError(target + ": unresolved build output")
            result[target] = self.root / module.path / matches[0]
        return result

    def extracted(
        self, targets: Iterable[str], module: Module = DOCS_MODULE
    ) -> dict[str, ModuleInfo]:
        """Build starlark_doc_extract outputs, by default this module's, and parse them."""
        return {
            target: parse_module(path.read_text())
            for target, path in self.outputs(targets, module).items()
        }

    def expansions(
        self, module: Module, labels: Iterable[str]
    ) -> dict[str, tuple[Target, ...]]:
        """
        Every rule emitted by each root's evaluated invocation, including the root, from
        one query for all roots.
        """
        labels = tuple(dict.fromkeys(labels))
        query = self.query(module, "kind(rule, siblings(set(" + " ".join(labels) + ")))")
        targets = query_targets(self.root, module, query)
        return {label: invocation(label, targets) for label in labels}

    def configured(
        self, module: Module, labels: Iterable[str], options: Iterable[str] = ()
    ) -> dict[str, ConfiguredTarget]:
        """Analyze labels together; Bazel reports an alias as its actual target.

        Callers select the lane, so missing SDKs fail instead of
        producing empty observations. Aliases are configured separately to keep
        their own label.
        """
        labels = tuple(dict.fromkeys(labels))
        options = tuple(options)

        def cquery(selected: tuple[str, ...]) -> dict[str, ConfiguredTarget]:
            return decode_configured(
                self.run(
                    module,
                    "cquery",
                    "config(set(" + " ".join(selected) + "), target)",
                    "--output=starlark",
                    "--universe_scope=" + ",".join(selected),
                    "--starlark:expr=" + _EVIDENCE,
                    *options,
                    profiled=True,
                )
            )

        observed = cquery(labels) if labels else {}
        result = {}
        for label in labels:
            if unqualified(label) in observed:
                result[label] = observed[unqualified(label)]
                continue
            actual = list(cquery((label,)).values())
            if len(actual) != 1:
                raise EvidenceError(label + ": expected exactly one configured target")
            result[label] = actual[0]
        return result

    def repository(
        self, module: Module, expression: str
    ) -> tuple[dict[str, Target], set[str]]:
        """Rules and public source files of generated repositories, by apparent label."""
        query = self.query(module, expression)
        rules = {
            target.label: target for target in query_targets(self.root, module, query)
        }
        sources = {
            source.attrib["name"]
            for source in query.findall("source-file")
            if any(
                item.attrib["name"] == "//visibility:public"
                for item in source.findall("visibility-label")
            )
        }
        return rules, sources

    def tests(self, labels: Iterable[str], module: Module = RULESET_MODULE) -> set[str]:
        """Evaluated Bazel tests among one module's labels, including test suites."""
        labels = sorted(labels)
        if not labels:
            return set()
        output = self.run(
            module,
            "query",
            "tests(set(" + " ".join(labels) + "))",
            "--output=label",
        )
        return set(output.split())


def behavior_tests(behavior: Mapping[str, list[Any]]) -> dict[str, set[str]]:
    """
    Group registered behavior tests by the module they run in, as API cases do.

    An entry is a label of the ruleset module or ``{"target": label, "module": path}``.
    """
    modules: dict[str, set[str]] = {}
    for tests in behavior.values():
        for test in tests:
            if isinstance(test, str):
                modules.setdefault(RULESET_DIR, set()).add(test)
            else:
                modules.setdefault(test.get("module", RULESET_DIR), set()).add(
                    test["target"]
                )
    return modules


def is_test(target: Target) -> bool:
    """Bazel requires test rule class names, and only those, to end in ``_test``."""
    return target.kind.endswith("_test")
