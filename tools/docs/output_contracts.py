"""Parse evaluated source contracts and compare them with evaluated Bazel evidence.

The tables are part of the API's Stardoc prose. This module never reads or evaluates
Starlark: callers supply the docstring emitted by starlark_doc_extract and the facts
Bazel reports for configured fixtures.
"""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from tools.ci.verification import PROFILE_LANES

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
    "Providers": ("name", "role", "availability"),
}
DEFAULT_KINDS = frozenset({"files", "executable", "test", "metadata", "repository"})
COMPANION_KINDS = frozenset(
    {"alias", "test", "executable", "files", "metadata", "library", "toolchain"}
)
# The lanes with API contract cases: docs, whose cases are the default, and the
# profile lanes.
DEFAULT_CONTRACT_LANE = "docs"
CONTRACT_LANES = (DEFAULT_CONTRACT_LANE, *PROFILE_LANES)
# The lane whose cases evaluate the consumer modules.
CONSUMER_MODULE_LANE = "host"
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
    providers: tuple[dict[str, str], ...] = ()


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


def _table(section: str, lines: list[str]) -> tuple[dict[str, str], ...]:
    lines = [line.strip() for line in lines if line.strip()]
    if lines == ["none"]:
        return ()
    if not lines:
        raise ValueError(f"{section}: require a table or explicit none")
    if any(not line.startswith("|") or not line.endswith("|") for line in lines):
        raise ValueError(f"{section}: expected a Markdown table or explicit none")
    rows = [[cell.strip() for cell in line[1:-1].split("|")] for line in lines]
    fields = SECTIONS[section]
    if tuple(rows[0]) != fields:
        raise ValueError(f"{section}: expected fields {', '.join(fields)}")
    if len(rows) < 3 or any(set(cell) - {"-", ":"} or not cell for cell in rows[1]):
        raise ValueError(f"{section}: require table separator and at least one row")
    result = []
    identities = set()
    for row in rows[2:]:
        if len(row) != len(fields) or not all(row):
            raise ValueError(f"{section}: missing or unknown fields")
        values = dict(zip(fields, row, strict=True))
        # A name may repeat across availabilities; defaults are keyed by kind.
        identity = (row[0], values["availability"])
        if identity in identities:
            raise ValueError(f"{section}: duplicate {row[0]}")
        identities.add(identity)
        result.append(values)
    return tuple(result)


def parse(doc: str) -> Contract:
    """Require explicit, typed contract sections in a Bazel-evaluated docstring."""
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
    for title in SECTIONS:
        if title not in sections:
            raise ValueError(f"{title}: missing section")
    contract = Contract(*(_table(title, sections[title]) for title in SECTIONS))
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
    if separator and repository.lstrip("@").removesuffix("+") in {"", "rules_godot"}:
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


def public_providers(target: ConfiguredTarget, providers: Mapping[str, str]) -> set[str]:
    """Observed providers that are public ruleset providers; others are not promised."""
    public = set(providers.values())
    return {provider_identity(key) for key in target.providers} & public


def compare(
    contract: Contract,
    target: ConfiguredTarget,
    *,
    test: bool,
    shared_library: bool = False,
    companions: Iterable[str] = (),
    conditions: Iterable[str] = (),
    providers: Mapping[str, str],
    forwarded_groups: bool = False,
) -> list[str]:
    """Reject missing promises and undocumented observed public interfaces.

    ``providers`` maps public ruleset provider names to their defining identity.
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
    documented = {
        providers[row["name"]]
        for row in active(contract.providers, conditions)
        if row["name"] in providers
    }
    errors.extend(
        _difference("provider", documented, public_providers(target, providers))
    )
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
                contract.providers,
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
