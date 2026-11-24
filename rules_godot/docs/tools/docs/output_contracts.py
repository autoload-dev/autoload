"""Parse evaluated source contracts and compare them with evaluated Bazel evidence.

The lists are part of the API's Stardoc prose. This module never reads or evaluates
Starlark: callers supply the docstring emitted by starlark_doc_extract and the facts
Bazel reports for configured fixtures.
"""

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from tools.ci.lanes import CONTRACT_LANES as MACHINE_LANES
from tools.docs.ruleset import MODULE

SECTIONS = {
    "Default outputs": ("kind", "cardinality", "availability", "behavior"),
    "Output groups": ("name", "contents", "availability", "prerequisites"),
    "Generated targets": (
        "name",
        "kind",
        "purpose",
        "reason",
        "visibility",
        "testonly",
        "prerequisites",
        "availability",
    ),
}
# The first line of an entry: `- kind (cardinality): behavior` for default outputs,
# `- `name`: contents` for output groups and `- `name` (kind): reason` for generated
# targets. Indented `- field: value` lines below it give the other fields; an omitted
# field has its default.
FIRST_LINES = {
    "Default outputs": re.compile(
        r"(?P<kind>[a-z_]+) \((?P<cardinality>[a-z]+)\): (?P<behavior>.+)"
    ),
    "Output groups": re.compile(r"`(?P<name>[^`]+)`: (?P<contents>.+)"),
    "Generated targets": re.compile(
        r"`(?P<name>[^`]+)` \((?P<kind>[a-z_]+)\): (?P<reason>.+)"
    ),
}
FIELD_DEFAULTS = {
    "availability": "always",
    "prerequisites": "none",
    "purpose": "operation",
    "visibility": "public",
    "testonly": "false",
}
DEFAULT_KINDS = frozenset({"files", "executable", "test", "metadata", "repository"})
COMPANION_KINDS = frozenset(
    {"alias", "test", "executable", "files", "metadata", "library", "toolchain"}
)
# The lanes with API contract cases: docs, whose cases are the default, and the
# profile lanes.
DEFAULT_CONTRACT_LANE = "docs"
CONTRACT_LANES = (DEFAULT_CONTRACT_LANE, *MACHINE_LANES)
# The lane whose cases evaluate the consumer modules.
CONSUMER_MODULE_LANE = "desktop"
REPOSITORY_KINDS = frozenset({"repository_rule_info", "module_extension_info"})


def behavior_lane(module: str) -> str:
    """
    The lane that resolves a module's behavior tests: one that evaluates the module anyway.

    The docs lane, part of the default hook, evaluates the ruleset module only.
    """
    return DEFAULT_CONTRACT_LANE if module == "." else CONSUMER_MODULE_LANE


@dataclass(frozen=True)
class Contract:
    defaults: tuple[dict[str, str], ...] = ()
    groups: tuple[dict[str, str], ...] = ()
    companions: tuple[dict[str, str], ...] = ()


@dataclass(frozen=True)
class Api:
    """One extracted public export: its Stardoc kind, contract and defining identity."""

    kind: str
    contract: Contract
    origin: str


@dataclass(frozen=True)
class ConfiguredTarget:
    """Interfaces observed by evaluated analysis, not promises copied from the docs."""

    label: str
    files: int
    runfiles: int
    executable: bool
    providers: frozenset[str]
    groups: frozenset[str]


def _entries(section: str, lines: list[str]) -> tuple[dict[str, str], ...]:
    """Read a section's list: entries, their indented fields and continuation lines."""
    fields = SECTIONS[section]
    entries: list[dict[str, str]] = []
    entry_indent = 0
    last = ""
    for line in lines:
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip())
        text = line.strip()
        if not entries or indent <= entry_indent:
            if not text.startswith("- "):
                raise ValueError(f"{section}: expected a list entry: {text}")
            match = FIRST_LINES[section].fullmatch(text[2:])
            if not match:
                raise ValueError(f"{section}: malformed entry: {text}")
            entries.append(match.groupdict())
            entry_indent = indent
            last = list(match.groupdict())[-1]
        elif text.startswith("- "):
            field, separator, value = text[2:].partition(": ")
            entry = entries[-1]
            if not separator or field not in fields or field in entry or not value:
                raise ValueError(f"{section}: unknown or repeated field: {text}")
            entry[field] = value
            last = field
        else:
            entries[-1][last] += " " + text
    if not entries:
        raise ValueError(f"{section}: an empty section is omitted")
    result = []
    identities = set()
    for entry in entries:
        values = {field: entry.get(field) or FIELD_DEFAULTS[field] for field in fields}
        # A name may repeat across availabilities; defaults are keyed by kind.
        identity = (values[fields[0]], values["availability"])
        if identity in identities:
            raise ValueError(f"{section}: duplicate {values[fields[0]]}")
        identities.add(identity)
        result.append(values)
    return tuple(result)


def parse(doc: str) -> Contract:
    """Read the typed contract sections of a Bazel-evaluated docstring.

    Default outputs is required; a section without entries is omitted.
    """
    sections: dict[str, list[str]] = {}
    active = None
    for line in doc.splitlines():
        stripped = line.strip()
        if stripped.startswith("### "):
            active = stripped[4:] if stripped[4:] in SECTIONS else None
            if active:
                if active in sections:
                    raise ValueError(f"{active}: duplicate section")
                sections[active] = []
        elif stripped.startswith("## ") or stripped in {"Args:", "Returns:"}:
            active = None
        elif active:
            sections[active].append(line)
    if "Default outputs" not in sections:
        raise ValueError("Default outputs: missing section")
    contract = Contract(
        *(
            _entries(title, sections[title]) if title in sections else ()
            for title in SECTIONS
        )
    )
    for row in contract.defaults:
        if row["kind"] not in DEFAULT_KINDS:
            raise ValueError("Default outputs: unknown kind " + row["kind"])
        if row["cardinality"] not in {"none", "one", "many"}:
            raise ValueError("Default outputs: invalid cardinality")
    for row in contract.companions:
        if row["kind"] not in COMPANION_KINDS:
            raise ValueError("Generated targets: invalid kind")
        if row["purpose"] not in {"operation", "test", "analysis_boundary"}:
            raise ValueError("Generated targets: invalid purpose " + row["purpose"])
        if (row["purpose"] == "test") != (row["kind"] == "test"):
            raise ValueError("Generated targets: test purpose requires test kind")
        if row["visibility"] not in {"public", "caller"}:
            raise ValueError("Generated targets: invalid visibility")
        if row["testonly"] not in {"true", "false", "inherit"}:
            raise ValueError("Generated targets: invalid testonly")
        if row["reason"] == "none":
            raise ValueError("Generated targets: require concrete reason")
    return contract


def active(rows: Iterable[dict[str, str]], conditions: Iterable[str]) -> list[dict]:
    """Rows available in a configuration with the given conditions."""
    conditions = set(conditions)
    return [row for row in rows if row["availability"] in conditions | {"always"}]


def provider_identity(key: str) -> str:
    """Drop the ruleset's repository prefix from an evaluated provider key."""
    repository, separator, rest = key.partition("//")
    if separator and repository.lstrip("@").removesuffix("+") in {"", MODULE}:
        return "//" + rest
    return key


def _has_provider(target: ConfiguredTarget, name: str) -> bool:
    return any(key == name or key.endswith("%" + name) for key in target.providers)


def kind_errors(
    kind: str, target: ConfiguredTarget, *, test: bool, shared_library: bool = False
) -> list[str]:
    """Compare a documented default/companion/entrypoint kind with evaluated semantics.

    ``test`` is Bazel's own test classification. A ``cc_binary`` with ``linkshared``
    exposes RunfilesSupport, but it links rather than runs.
    """
    errors = []
    if kind == "test" and not test:
        errors.append("promised test is not an evaluated Bazel test")
    if kind != "test" and test:
        errors.append("undocumented evaluated test behavior")
    if kind in {"test", "executable"}:
        if not target.executable or not target.runfiles:
            errors.append("missing promised executable or runfiles")
    elif target.executable and not shared_library:
        errors.append("undocumented executable behavior")
    if kind in {"metadata", "toolchain"} and target.files:
        errors.append(kind + " must not produce default files")
    if kind == "library" and not _has_provider(target, "CcInfo"):
        errors.append("library lacks CcInfo")
    if kind == "toolchain" and not _has_provider(target, "ToolchainInfo"):
        errors.append("toolchain lacks ToolchainInfo")
    return errors


def _difference(kind: str, expected: set[str], actual: set[str]) -> list[str]:
    return [
        f"missing documented {kind}: {name}" for name in sorted(expected - actual)
    ] + [f"undocumented {kind}: {name}" for name in sorted(actual - expected)]


def compare(
    contract: Contract,
    target: ConfiguredTarget,
    *,
    test: bool,
    shared_library: bool = False,
    companions: Iterable[str] = (),
    conditions: Iterable[str] = (),
    forwarded_groups: bool = False,
) -> list[str]:
    """Reject missing promises and undocumented observed public interfaces.

    Groups whose name starts with ``_`` are Bazel/implementation groups. A root that
    forwards an upstream target's groups is only checked for its documented ones.
    """
    errors = []
    defaults = active(contract.defaults, conditions)
    if len(defaults) != 1:
        return ["require exactly one active default output contract"]
    row = defaults[0]
    if row["cardinality"] == "one" and target.files != 1:
        errors.append("default output cardinality must be one")
    elif row["cardinality"] == "none" and target.files:
        errors.append("default output cardinality must be none")
    errors.extend(
        kind_errors(row["kind"], target, test=test, shared_library=shared_library)
    )
    groups = {row["name"] for row in active(contract.groups, conditions)}
    observed = {name for name in target.groups if not name.startswith("_")}
    if forwarded_groups:
        observed &= groups
    errors.extend(_difference("group", groups, observed))
    errors.extend(
        _difference(
            "companion",
            {row["name"] for row in active(contract.companions, conditions)},
            set(companions),
        )
    )
    return errors


def is_repository_api(api: Api) -> bool:
    """Repository rules, module extensions and helper functions whose only output is repositories."""
    if api.kind in REPOSITORY_KINDS:
        return True
    return api.kind == "func_info" and [row["kind"] for row in api.contract.defaults] == [
        "repository"
    ]


def coverage_errors(
    apis: Mapping[str, Api],
    cases: Mapping[str, dict],
    behavior: Mapping[str, list[str]],
) -> list[str]:
    """Require every public export to own configured cases and companion tests."""
    errors = []
    for identity, api in apis.items():
        if api.kind == "provider_info":
            continue
        registered = [
            case for key, case in cases.items() if key.partition("#")[0] == identity
        ]
        if not registered:
            errors.append(f"{identity}: missing configured case")
        covered = {
            condition for case in registered for condition in case.get("conditions", [])
        }
        contract = api.contract
        promised = {
            row["availability"]
            for section in (
                contract.defaults,
                contract.groups,
                contract.companions,
            )
            for row in section
        } - {"always"}
        for condition in sorted(promised - covered):
            errors.append(
                f"{identity}: conditional availability {condition!r} has no configured case"
            )
        if contract.companions and not behavior.get(identity):
            errors.append(
                f"{identity}: public companions need a registered behavior test"
            )
    for key, case in cases.items():
        api = apis.get(key.partition("#")[0])
        if api is None:
            errors.append(f"{key}: case refers to unknown API")
            continue
        if case.get("lane", DEFAULT_CONTRACT_LANE) not in CONTRACT_LANES:
            errors.append(f"{key}: unknown required lane")
        if is_repository_api(api) != ("entrypoints" in case):
            errors.append(f"{key}: repository APIs, and only those, use entrypoint cases")
        elif "entrypoints" not in case and not case.get("target"):
            errors.append(f"{key}: missing evaluated target")
    for identity in behavior:
        if identity not in apis:
            errors.append(f"{identity}: behavior test refers to unknown API")
    return errors


def has_consumer_visibility(
    label: str, visibility: Iterable[str], *, symbolic_macro: bool = False
) -> bool:
    """Recognize access outside a package or evaluated symbolic-macro scope."""
    repository, _, relative = label.partition("//")
    package = relative.partition(":")[0]
    private = {"//visibility:private"}
    if not symbolic_macro:
        private.add(repository + "//" + package + ":__pkg__")
    return any(grant not in private for grant in visibility)


def is_shared_library(kind: str, booleans: Mapping[str, bool]) -> bool:
    """An evaluated cc_binary with linkshared declares linking despite exposing RunfilesSupport."""
    return kind == "cc_binary" and booleans.get("linkshared", False)
