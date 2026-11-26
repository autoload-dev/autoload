"""
The rules of a recipe repository's BUILD file as data, and their Starlark text.

Rendering builds rules and constants as values, so the runtime variants of a recipe merge
as data: a rule that the variants declare alike stays one rule, and an attribute that
differs becomes a select() on the variants' config_settings. Only write() turns them into
text.
"""

from collections.abc import Iterable, Mapping, Sequence
from typing import NamedTuple


class Ref(NamedTuple):
    """A reference to a constant of the BUILD file, by its name."""

    name: str


class Plus(NamedTuple):
    """Values added together, such as a constant list and a literal one."""

    parts: tuple[object, ...]


class Select(NamedTuple):
    """A select() of each config_setting's value; //conditions:default comes last."""

    branches: tuple[tuple[str, object], ...]


DEFAULT = "//conditions:default"


class Rule(NamedTuple):
    """
    One rule of the BUILD file.

    fixed names the attributes Bazel cannot select, such as declared outputs and the
    values a macro reads; name, visibility and tags never can.
    """

    kind: str
    name: str
    attrs: dict[str, object]
    fixed: frozenset[str] = frozenset()


ALWAYS_FIXED = frozenset({"visibility", "tags"})


class Constants:
    """
    The constants of a BUILD file: one per distinct value, named by the first use.

    The variants of a recipe share one pool, so a reference compares alike wherever the
    values do.
    """

    def __init__(self) -> None:
        self.values: dict[str, list[str]] = {}
        self._names: dict[tuple[str, ...], str] = {}
        self._counts: dict[str, int] = {}

    def ref(self, prefix: str, value: Sequence[str]) -> Ref:
        key = tuple(value)
        if key not in self._names:
            count = self._counts.get(prefix, 0)
            self._counts[prefix] = count + 1
            name = f"{prefix}_{count}"
            self._names[key] = name
            self.values[name] = list(key)
        return Ref(self._names[key])


def value_text(value: object) -> str:
    """The Starlark text of a value."""
    if isinstance(value, Ref):
        return value.name
    if isinstance(value, Plus):
        return " + ".join(value_text(part) for part in value.parts)
    if isinstance(value, Select):
        entries = ", ".join(
            f"{setting!r}: {value_text(item)}" for setting, item in value.branches
        )
        return "select({" + entries + "})"
    if isinstance(value, (list, tuple)):
        return "[" + ", ".join(value_text(item) for item in value) + "]"
    if isinstance(value, dict):
        entries = ", ".join(
            f"{value_text(key)}: {value_text(item)}" for key, item in value.items()
        )
        return "{" + entries + "}"
    return repr(value)


def rule_text(rule: Rule) -> str:
    """The Starlark call of a rule, its attributes in their order after its name."""
    attributes = [f"name = {rule.name!r}"] + [
        f"{key} = {value_text(value)}" for key, value in rule.attrs.items()
    ]
    return f"{rule.kind}({', '.join(attributes)})"


def write(
    header: Iterable[str], constants: Mapping[str, Sequence[str]], rules: Iterable[Rule]
) -> str:
    """The BUILD file: the loads and package statements, the constants, then the rules."""
    statements = [
        *header,
        *(f"{name} = {list(value)!r}" for name, value in constants.items()),
        *(rule_text(rule) for rule in rules),
    ]
    return "\n\n".join(statements) + "\n"
