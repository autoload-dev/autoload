"""RG006: documented Bazel commands name targets that exist."""

import re
from collections.abc import Iterable
from pathlib import Path

from tools.conventions.context import Context, Location
from tools.conventions.framework import Finding, RuleInfo
from tools.ruleset import REPO

# Only Bazel build/run/test command arguments are labels here, not source snippets,
# URLs, query expressions or Godot resource paths.
COMMAND = re.compile(r"\bbazel(?:isk)?\s+(?:build|run|test)\s+([^`\n]+)")
LABEL = re.compile(rf"(?<![\w/@:])(?:{re.escape(REPO)})?//[\w./-]*(?::[\w.*+/-]+)?")
# Wildcards that name every target of a package which exists.
WILDCARDS = {"all", "*", "all-targets"}


def command_labels(text: str) -> list[tuple[int, str]]:
    """Return each command label with the line on which its command starts."""
    labels: list[tuple[int, str]] = []
    command, start = "", 0
    for number, line in enumerate(text.splitlines(), 1):
        if not command:
            start = number
        if line.endswith("\\"):
            command += line[:-1] + " "
            continue
        labels.extend((start, label) for label in _labels(command + line))
        command = ""
    labels.extend((start, label) for label in _labels(command))
    return labels


def _labels(line: str) -> Iterable[str]:
    for command in COMMAND.finditer(line):
        # Everything after -- is an application's argument, not Bazel's.
        arguments = command[1].split(" -- ", 1)[0].split(" #", 1)[0]
        for match in LABEL.finditer(arguments):
            if "..." in match[0]:
                continue
            # A sentence may end right after the label.
            label = match[0].removesuffix(".")
            if re.match(r"//path/to(?:[/:]|$)", label.removeprefix(REPO)):
                continue
            yield label


class CommandLabels:
    info = RuleInfo(
        "RG006",
        "Documented commands name existing targets",
        "docs/public/conventions.md#rg006",
    )

    def evaluate(self, context: Context) -> Iterable[Finding]:
        for name in context.workspace.documents:
            owner = context.workspace.owner(name)
            for line, label in command_labels(context.workspace.text(name)):
                problem = self._problem(context, owner, label)
                if problem:
                    yield Finding(Location(name, line), f"{label}: {problem}")

    def _problem(self, context: Context, owner: Path, label: str) -> str | None:
        local = label.removeprefix(REPO)
        ruleset = local != label
        # Root-local labels in consumer templates have no package context.
        if local.startswith("//:") and owner == Path(".") and not ruleset:
            return None
        package, _, target = local[2:].partition(":")
        # A command names its document's module first; nested modules are explicit.
        candidates = [
            module for module in context.workspace.modules if package in module.packages
        ]
        if ruleset:
            candidates = [module for module in candidates if module.path == Path(".")]
        elif owner != Path(".") and owner in {module.path for module in candidates}:
            candidates = [module for module in candidates if module.path == owner]
        if len(candidates) != 1:
            return (
                f"expected one owning module for package {package!r}, "
                f"found {len(candidates)}"
            )
        module = candidates[0]
        target = target or package.rsplit("/", 1)[-1]
        if target in WILDCARDS:
            return None
        wanted = f"//{package}:{target}"
        if not any(rule.label == wanted for rule in context.bazel.rules(module)):
            return f"no rule {target!r} in package {package!r} of module {module.path}"
        return None
