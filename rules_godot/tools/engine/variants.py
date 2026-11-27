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

from tools.engine.build_file import ALWAYS_FIXED, DEFAULT, Plus, Ref, Rule, Select

# ==== Merging =================================================================


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


def _attribute(rules: Mapping[str, Rule], name: str, fixed: bool) -> object:
    """One attribute of a merged rule; rules maps each declaring variant to its rule."""
    values = {
        setting: rule.attrs[name] for setting, rule in rules.items() if name in rule.attrs
    }
    if len(values) == len(rules) and _alike(values.values()):
        return next(iter(values.values()))
    if fixed:
        first = next(iter(rules.values()))
        raise ValueError(
            f"The runtime variants declare {first.name} with different {name}"
        )
    empty = _empty(values.values())
    return _select({setting: values.get(setting, empty) for setting in rules})


def _merged_rule(rules: Mapping[str, Rule]) -> Rule:
    """One rule that the variants in rules declare, with select() where they differ."""
    first = next(iter(rules.values()))
    if not _alike(rule.kind for rule in rules.values()):
        raise ValueError(
            f"The runtime variants declare {first.name} with different rules"
        )
    fixed = ALWAYS_FIXED.union(*(rule.fixed for rule in rules.values()))
    names = dict.fromkeys(name for rule in rules.values() for name in rule.attrs)
    attrs = {name: _attribute(rules, name, name in fixed) for name in names}
    return Rule(first.kind, first.name, attrs, first.fixed)


def _by_name(
    base: Sequence[Rule], variants: Mapping[str, Sequence[Rule]]
) -> dict[str, dict[str, Rule]]:
    """Each rule's declarations, by its name and then by the declaring variant's setting."""
    declared: dict[str, dict[str, Rule]] = {}
    for setting, rules in {DEFAULT: base, **variants}.items():
        for rule in rules:
            declared.setdefault(rule.name, {})[setting] = rule
    return declared


def merge(base: Sequence[Rule], variants: Mapping[str, Sequence[Rule]]) -> list[Rule]:
    """
    Return the rules of one package that declares the base and every variant.

    Args:
        base: The rules of the recipe without a runtime profile.
        variants: Each variant's rules, by the label of the config_setting that selects it.

    Returns:
        Each rule once, in the order the base and then the variants declare them.
    """
    return [
        next(iter(rules.values())) if _alike(rules.values()) else _merged_rule(rules)
        for rules in _by_name(base, variants).values()
    ]


def _presence(libraries: Mapping[str, Iterable[str]]) -> dict[str, tuple[str, ...]]:
    """The variants that compile each library, by the library's name."""
    presence: dict[str, list[str]] = {}
    for variant, names in libraries.items():
        for name in names:
            presence.setdefault(name, []).append(variant)
    return {name: tuple(variants) for name, variants in presence.items()}


def presence_scopes(libraries: Mapping[str, Iterable[str]]) -> dict[str, str]:
    """
    Return the define analysis scope of each library: empty where every variant compiles it.

    A shard of the analysis holds libraries that the same variants compile, so a variant
    builds no shard with another's sources.

    Args:
        libraries: The names of the libraries each variant compiles, by variant.
    """
    presence = _presence(libraries)
    every = tuple(libraries)
    tags = {
        variants: "" if variants == every else f"p{index}__"
        for index, variants in enumerate(sorted(set(presence.values())))
    }
    return {name: tags[variants] for name, variants in presence.items()}


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


def _renamed(rule: Rule, names: Mapping[str, str]) -> Rule:
    """A rule with its name and the labels it uses renamed by names."""
    attrs = {key: _relabeled(value, names) for key, value in rule.attrs.items()}
    return Rule(rule.kind, names.get(rule.name, rule.name), attrs, rule.fixed)


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
    result = [_renamed(rule, names) for rule in rules]
    for target in targets:
        result += _stand_ins(target, names[target], errors)
    return result
