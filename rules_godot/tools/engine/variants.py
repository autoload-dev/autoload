"""
Merge the BUILD statements of a recipe's runtime variants into one package.

A runtime variant is the recipe configured with the build options of a registered runtime
profile. Each variant's graph renders to statements as the recipe's own does; merge()
declares a target that the variants declare alike once, and selects an attribute that
differs on the variant's config_setting. A target keeps its name in every variant, so an
object that two variants compile alike keeps one label and, under path mapping, one cache
key in both.

Sections: Statements, Merging, Unpinned variants.
"""

import ast
from collections.abc import Iterable, Iterator, Mapping, Sequence
from typing import NamedTuple

# ==== Statements ==============================================================


class _Statement(NamedTuple):
    """A BUILD statement: a rule call with a name, a constant, or anything else."""

    kind: str
    key: str
    text: str
    node: ast.AST | None


def _keyword(call: ast.Call, name: str) -> ast.expr | None:
    return next((item.value for item in call.keywords if item.arg == name), None)


def _statement(text: str) -> _Statement:
    body = ast.parse(text).body
    node = body[0] if len(body) == 1 else None
    if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
        return _Statement("constant", node.targets[0].id, text, node)
    if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
        name = _keyword(node.value, "name")
        if isinstance(name, ast.Constant) and isinstance(node.value.func, ast.Name):
            return _Statement("rule", str(name.value), text, node.value)
    return _Statement("other", text, text, None)


class _Renamer(ast.NodeTransformer):
    """Rename the constants a statement references."""

    def __init__(self, names: Mapping[str, str]) -> None:
        self.names = names

    def visit_Name(self, node: ast.Name) -> ast.Name:
        return ast.Name(self.names.get(node.id, node.id), node.ctx)


# ==== Merging =================================================================

# Attributes Bazel cannot select: names, declared outputs, and what the generated
# repository's macros read.
_FIXED = frozenset(
    {"name", "visibility", "tags", "outs", "build", "hash", "timestamp", "class_profile"}
)

_DEFAULT = "//conditions:default"


def _empty(values: Iterable[ast.expr]) -> ast.expr:
    """The value of an attribute that a variant leaves unset, by the type others give it."""
    for value in values:
        if isinstance(value, (ast.List, ast.BinOp)):
            return ast.List([], ast.Load())
        if isinstance(value, ast.Dict):
            return ast.Dict([], [])
        if isinstance(value, ast.Constant):
            return ast.Constant(type(value.value)())
    raise ValueError("Cannot tell the type of an attribute some variants leave unset")


def _select(branches: Mapping[str, ast.expr], default: ast.expr) -> str:
    """A select() of the branches whose value differs from the default."""
    differing = {
        setting: value
        for setting, value in branches.items()
        if ast.dump(value) != ast.dump(default)
    }
    if not differing:
        return ast.unparse(default)
    entries = [
        f"{setting!r}: {ast.unparse(value)}" for setting, value in differing.items()
    ]
    entries.append(f"{_DEFAULT!r}: {ast.unparse(default)}")
    return "select({" + ", ".join(entries) + "})"


def _fixed(rule: str, name: str, values: Mapping[str, ast.expr | None]) -> str:
    """An attribute Bazel cannot select, which every variant must declare alike."""
    present = [value for value in values.values() if value is not None]
    if len(present) != len(values) or len({ast.dump(value) for value in present}) != 1:
        raise ValueError(f"The runtime variants declare {rule} with different {name}")
    return ast.unparse(present[0])


def _attribute(rule: str, name: str, values: Mapping[str, ast.expr | None]) -> str:
    """One attribute of a merged rule; values maps each declaring variant to its value."""
    if name in _FIXED:
        return _fixed(rule, name, values)
    present = [value for value in values.values() if value is not None]
    # Only a variant that leaves the attribute unset takes the empty value.
    empty = _empty(present) if len(present) != len(values) else ast.Constant(None)
    resolved = {
        setting: value if value is not None else empty
        for setting, value in values.items()
    }
    default = resolved.pop(_DEFAULT, None) or next(iter(resolved.values()))
    return _select(resolved, default)


def _call_text(call: ast.Call) -> str:
    """A rule call as the renderer writes it: keyword arguments with spaces around =."""
    arguments = ", ".join(
        f"{item.arg} = {ast.unparse(item.value)}" for item in call.keywords
    )
    return f"{ast.unparse(call.func)}({arguments})"


def _merged_rule(name: str, calls: Mapping[str, ast.Call]) -> str:
    """One rule that the variants in calls declare, with select() where they differ."""
    kinds = {ast.unparse(call.func) for call in calls.values()}
    if len(kinds) != 1:
        raise ValueError(f"The runtime variants declare {name} with different rules")
    attributes = list(
        dict.fromkeys(item.arg for call in calls.values() for item in call.keywords)
    )
    rendered = [
        f"{attribute} = "
        + _attribute(
            name,
            str(attribute),
            {setting: _keyword(call, str(attribute)) for setting, call in calls.items()},
        )
        for attribute in attributes
    ]
    return f"{kinds.pop()}({', '.join(rendered)})"


class _Variant(NamedTuple):
    setting: str
    statements: list[_Statement]


def _constants(
    variants: Sequence[_Variant],
) -> tuple[list[str], dict[str, dict[str, str]]]:
    """
    Return the merged constants and each variant's renaming of its own.

    The base keeps its constants. A variant's constant takes the name of the first one of
    its value, or else a name of its own, prefixed with the variant's index.
    """
    by_value: dict[str, str] = {}
    lines: list[str] = []
    renames: dict[str, dict[str, str]] = {}
    for index, variant in enumerate(variants):
        renames[variant.setting] = {}
        for statement in variant.statements:
            if statement.kind != "constant" or not isinstance(statement.node, ast.Assign):
                continue
            value = ast.dump(statement.node.value)
            if not index:
                # The base keeps its constants, also those of one value, but compares by
                # the first one's name.
                renames[variant.setting][statement.key] = by_value.setdefault(
                    value, statement.key
                )
                lines.append(statement.text)
                continue
            if value not in by_value:
                by_value[value] = f"_V{index - 1}{statement.key}"
                lines.append(f"{by_value[value]} = {ast.unparse(statement.node.value)}")
            renames[variant.setting][statement.key] = by_value[value]
    return lines, renames


def _calls(
    variant: _Variant, renames: Mapping[str, str]
) -> Iterator[tuple[_Statement, ast.Call]]:
    """A variant's rules, with its constants renamed to the merged ones."""
    renamer = _Renamer(renames)
    for statement in variant.statements:
        if statement.kind == "rule" and isinstance(statement.node, ast.Call):
            yield statement, renamer.visit(statement.node)


def _rules(
    variants: Sequence[_Variant], renames: Mapping[str, Mapping[str, str]]
) -> list[str]:
    """Each rule once, in the order the variants declare them."""
    declared: dict[str, dict[str, ast.Call]] = {}
    # The base's text where it declares a rule alike, as a recipe without variants.
    texts: dict[str, str] = {}
    for variant in variants:
        for statement, call in _calls(variant, renames[variant.setting]):
            declared.setdefault(statement.key, {})[variant.setting] = call
            if variant.setting == _DEFAULT:
                texts[statement.key] = statement.text
    return [
        _merged_rule(name, calls)
        if len({ast.dump(call) for call in calls.values()}) != 1
        else texts.get(name) or _call_text(next(iter(calls.values())))
        for name, calls in declared.items()
    ]


def merge(base: Sequence[str], variants: Mapping[str, Sequence[str]]) -> list[str]:
    """
    Return the statements of one package that declares the base and every variant.

    Args:
        base: The statements of the recipe without a runtime profile.
        variants: Each variant's statements, by the label of the config_setting that
            selects it.

    Returns:
        The other statements, such as loads, once each; the constants; the rules.
    """
    parsed = [_Variant(_DEFAULT, [_statement(text) for text in base])] + [
        _Variant(setting, [_statement(text) for text in statements])
        for setting, statements in variants.items()
    ]
    others = dict.fromkeys(
        statement.text
        for variant in parsed
        for statement in variant.statements
        if statement.kind == "other"
    )
    constants, renames = _constants(parsed)
    return [*others, *constants, *_rules(parsed, renames)]


def presence_scopes(libraries: Mapping[str, Iterable[str]]) -> dict[str, str]:
    """
    Return the define analysis scope of each library: empty where every variant compiles it.

    A shard of the analysis holds libraries that the same variants compile, so a variant
    builds no shard with another's sources.

    Args:
        libraries: The names of the libraries each variant compiles, by variant.
    """
    presence: dict[str, list[str]] = {}
    for variant, names in libraries.items():
        for name in names:
            presence.setdefault(name, []).append(variant)
    sets = sorted({tuple(variants) for variants in presence.values()})
    every = tuple(libraries)
    tags = {
        variants: "" if variants == every else f"p{index}__"
        for index, variants in enumerate(sets)
    }
    return {name: tags[tuple(variants)] for name, variants in presence.items()}


# ==== Unpinned variants =======================================================


class _Relabel(ast.NodeTransformer):
    """Rename the engine targets and the references to them."""

    def __init__(self, names: Mapping[str, str]) -> None:
        self.names = names

    def visit_Constant(self, node: ast.Constant) -> ast.Constant:
        if isinstance(node.value, str) and node.value.startswith(":"):
            return ast.Constant(":" + self.names.get(node.value[1:], node.value[1:]))
        return node

    def visit_keyword(self, node: ast.keyword) -> ast.keyword:
        if node.arg == "name" and isinstance(node.value, ast.Constant):
            return ast.keyword(
                "name", ast.Constant(self.names.get(node.value.value, node.value.value))
            )
        return ast.keyword(node.arg, self.visit(node.value))


def _relabeled(statements: Sequence[str], names: Mapping[str, str]) -> list[str]:
    """The statements with the engine targets renamed, also where rules name them."""
    relabel = _Relabel(names)
    result = []
    for text in statements:
        statement = _statement(text)
        if statement.kind == "rule" and isinstance(statement.node, ast.Call):
            text = _call_text(relabel.visit(statement.node))
        result.append(text)
    return result


def _stand_ins(target: str, pinned: str, errors: Mapping[str, str]) -> list[str]:
    """An engine target's alias: the failing stand-in of each unpinned variant, or the pinned target."""
    lines = []
    branches = {}
    for setting, message in errors.items():
        name = f"_unpinned_{setting.rpartition('_')[2]}_{target}"
        lines.append(f"godot_unpinned_recipe(name = {name!r}, message = {message!r})")
        branches[setting] = f":{name}"
    branches[_DEFAULT] = ":" + pinned
    return [*lines, f"alias(name = {target!r}, actual = select({branches!r}))"]


def unpinned_variants(
    statements: Sequence[str], targets: Sequence[str], errors: Mapping[str, str]
) -> list[str]:
    """
    Return the statements with the engine targets failing for the variants in errors.

    The engine targets take other names; an alias of each public name selects the target
    of a variant without a pin, which fails with its message, or else the pinned target.

    Args:
        statements: The merged statements.
        targets: The public engine targets, such as godot and engine_library.
        errors: The message of each variant that has no current pin, by its setting.
    """
    if not errors:
        return list(statements)
    names = {target: "_pinned_" + target for target in targets}
    result = _relabeled(statements, names)
    for target in targets:
        result += _stand_ins(target, names[target], errors)
    return result
