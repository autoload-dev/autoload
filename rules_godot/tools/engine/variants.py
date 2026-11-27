"""
Merge the rules of a recipe's runtime variants into one package.

A runtime variant is the recipe configured with the build options of a registered runtime
profile. Each variant's graph renders to rules as the recipe's own does, with constants
from one shared pool; merge() declares a rule that the variants declare alike once, and
selects an attribute that differs on the variant's config_setting. A target keeps its name
in every variant, so an object that two variants compile alike keeps one label and, under
path mapping, one cache key in both.

Sections: Merging, Unpinned variants.
"""

from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from tools.engine.build_file import ALWAYS_FIXED, DEFAULT, Plus, Ref, Rule, Select

# ==== Merging =================================================================

# A variant that leaves an attribute unset.
_UNSET = object()


def _empty(values: Iterable[object]) -> object:
    """The value of an attribute that a variant leaves unset, by the type others give it."""
    for value in values:
        if isinstance(value, (list, Plus, Ref)):
            return []
        if isinstance(value, (dict, str, bool)):
            return type(value)()
    raise ValueError("Cannot tell the type of an attribute some variants leave unset")


def _alike(values: Iterable[object]) -> bool:
    values = list(values)
    return all(value == values[0] for value in values)


def _select(values: Mapping[str, object]) -> Select:
    """A select() of each variant's value; the base's, or else the first one's, is the default."""
    resolved = dict(values)
    default = resolved.pop(DEFAULT, next(iter(resolved.values())))
    branches = [
        (setting, value) for setting, value in resolved.items() if value != default
    ]
    return Select((*branches, (DEFAULT, default)))


def _attribute(rule: str, name: str, values: Mapping[str, object], fixed: bool) -> object:
    """One attribute of a merged rule; values maps each declaring variant to its value."""
    first = next(iter(values.values()))
    if _alike(values.values()) and first is not _UNSET:
        return first
    if fixed:
        raise ValueError(f"The runtime variants declare {rule} with different {name}")
    empty = _empty(value for value in values.values() if value is not _UNSET)
    return _select(
        {
            setting: empty if value is _UNSET else value
            for setting, value in values.items()
        }
    )


def _values(rules: Mapping[str, Rule], name: str) -> dict[str, Any]:
    """Each variant's value of one attribute, by the variant's setting; _UNSET where absent."""
    return {setting: rule.attrs.get(name, _UNSET) for setting, rule in rules.items()}


def _merged_rule(rules: Mapping[str, Rule]) -> Rule:
    """One rule that the variants in rules declare, with select() where they differ."""
    first = next(iter(rules.values()))
    if not _alike(rule.kind for rule in rules.values()):
        raise ValueError(
            f"The runtime variants declare {first.name} with different rules"
        )
    fixed = ALWAYS_FIXED.union(*(rule.fixed for rule in rules.values()))
    names = dict.fromkeys(name for rule in rules.values() for name in rule.attrs)
    attrs = {
        name: _attribute(first.name, name, _values(rules, name), name in fixed)
        for name in names
    }
    return Rule(first.kind, first.name, attrs, first.fixed)


def merge(base: Sequence[Rule], variants: Mapping[str, Sequence[Rule]]) -> list[Rule]:
    """
    Return the rules of one package that declares the base and every variant.

    Args:
        base: The rules of the recipe without a runtime profile.
        variants: Each variant's rules, by the label of the config_setting that selects it.

    Returns:
        Each rule once, in the order the base and then the variants declare them.
    """
    declared: dict[str, dict[str, Rule]] = {}
    for setting, rules in {DEFAULT: base, **variants}.items():
        for rule in rules:
            declared.setdefault(rule.name, {})[setting] = rule
    return [
        next(iter(rules.values())) if _alike(rules.values()) else _merged_rule(rules)
        for rules in declared.values()
    ]


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


def _relabeled(value: object, names: Mapping[str, str]) -> object:
    """A value with the labels of renamed targets renamed."""
    if isinstance(value, str) and value.startswith(":"):
        return ":" + names.get(value[1:], value[1:])
    if isinstance(value, list):
        return [_relabeled(item, names) for item in value]
    if isinstance(value, Select):
        return Select(
            tuple((key, _relabeled(item, names)) for key, item in value.branches)
        )
    return value


def _stand_ins(target: str, pinned: str, errors: Mapping[str, str]) -> list[Rule]:
    """An engine target's alias: the failing stand-in of each unpinned variant, or the pinned target."""
    rules = []
    branches = []
    for setting, message in errors.items():
        name = f"_unpinned_{setting.rpartition('_')[2]}_{target}"
        rules.append(Rule("godot_unpinned_recipe", name, {"message": message}))
        branches.append((setting, f":{name}"))
    actual = Select((*branches, (DEFAULT, ":" + pinned)))
    return [*rules, Rule("alias", target, {"actual": actual})]


def unpinned_variants(
    rules: Sequence[Rule], targets: Sequence[str], errors: Mapping[str, str]
) -> list[Rule]:
    """
    Return the rules with the engine targets failing for the variants in errors.

    The engine targets take other names; an alias of each public name selects the target
    of a variant without a pin, which fails with its message, or else the pinned target.

    Args:
        rules: The merged rules.
        targets: The public engine targets, such as godot and engine_library.
        errors: The message of each variant that has no current pin, by its setting.
    """
    if not errors:
        return list(rules)
    names = {target: "_pinned_" + target for target in targets}
    result = [
        Rule(
            rule.kind,
            names.get(rule.name, rule.name),
            {key: _relabeled(value, names) for key, value in rule.attrs.items()},
            rule.fixed,
        )
        for rule in rules
    ]
    for target in targets:
        result += _stand_ins(target, names[target], errors)
    return result
