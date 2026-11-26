"""Parse evaluated source contracts and compare them with evaluated Bazel evidence.

The lists are part of the API's Stardoc prose. This module never reads or evaluates
Starlark: callers supply the docstring emitted by starlark_doc_extract and the facts
Bazel reports for configured fixtures.

Sections: Contract grammar, Evaluated comparison, Coverage.
"""

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from tools.ci.lanes import CONTRACT_LANES as MACHINE_LANES
from tools.docs.ruleset import MODULE
from tools.setup.modules import RULESET

# ==== Contract grammar ========================================================


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


@dataclass(frozen=True)
class Contract:
    defaults: tuple[dict[str, str], ...] = ()
    groups: tuple[dict[str, str], ...] = ()
    companions: tuple[dict[str, str], ...] = ()


def _first_line(section: str, text: str) -> dict[str, str]:
    """Read an entry's first line: `- ` and the section's pattern."""
    if not text.startswith("- "):
        raise ValueError(f"{section}: expected a list entry: {text}")
    match = FIRST_LINES[section].fullmatch(text[2:])
    if not match:
        raise ValueError(f"{section}: malformed entry: {text}")
    return match.groupdict()


def _field(section: str, entry: Mapping[str, str], text: str) -> tuple[str, str]:
    """Read an indented `- field: value` line that adds a field of the section."""
    field, separator, value = text[2:].partition(": ")
    new = field in SECTIONS[section] and field not in entry
    complete = bool(separator and value)
    if not (new and complete):
        raise ValueError(f"{section}: unknown or repeated field: {text}")
    return field, value


def _section_entries(section: str, lines: list[str]) -> list[dict[str, str]]:
    """Group a section's lines into entries with their fields and continuation lines."""
    entries: list[dict[str, str]] = []
    entry_indent = 0
    last = ""
    for line in lines:
        text = line.strip()
        if not text:
            continue
        indent = len(line) - len(line.lstrip())
        if not entries or indent <= entry_indent:
            entries.append(_first_line(section, text))
            entry_indent = indent
            last = list(entries[-1])[-1]
        elif text.startswith("- "):
            field, value = _field(section, entries[-1], text)
            entries[-1][field] = value
            last = field
        else:
            entries[-1][last] += " " + text
    return entries


def _with_defaults(
    section: str, entries: list[dict[str, str]]
) -> tuple[dict[str, str], ...]:
    """Fill omitted fields with their defaults and reject duplicate entries."""
    fields = SECTIONS[section]
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


def _entries(section: str, lines: list[str]) -> tuple[dict[str, str], ...]:
    """Read a section's list: entries, their indented fields and continuation lines."""
    entries = _section_entries(section, lines)
    if not entries:
        raise ValueError(f"{section}: an empty section is omitted")
    return _with_defaults(section, entries)


def _open_section(sections: dict[str, list[str]], title: str) -> str | None:
    """Start collecting a contract section; other subsections are no contract."""
    if title not in SECTIONS:
        return None
    if title in sections:
        raise ValueError(f"{title}: duplicate section")
    sections[title] = []
    return title


def _sections(doc: str) -> dict[str, list[str]]:
    """Collect the lines of each contract section of a docstring, keyed by title."""
    sections: dict[str, list[str]] = {}
    current = None
    for line in doc.splitlines():
        stripped = line.strip()
        if stripped.startswith("### "):
            current = _open_section(sections, stripped[4:])
        elif stripped.startswith("## ") or stripped in {"Args:", "Returns:"}:
            current = None
        elif current:
            sections[current].append(line)
    return sections


def _require(section: str, checks: Iterable[tuple[bool, str]]) -> None:
    """Raise the first failed check's problem, in the order given."""
    for valid, problem in checks:
        if not valid:
            raise ValueError(f"{section}: {problem}")


def _check_default(row: Mapping[str, str]) -> None:
    _require(
        "Default outputs",
        (
            (row["kind"] in DEFAULT_KINDS, "unknown kind " + row["kind"]),
            (row["cardinality"] in {"none", "one", "many"}, "invalid cardinality"),
        ),
    )


def _check_companion(row: Mapping[str, str]) -> None:
    purpose = row["purpose"]
    _require(
        "Generated targets",
        (
            (row["kind"] in COMPANION_KINDS, "invalid kind"),
            (
                purpose in {"operation", "test", "analysis_boundary"},
                "invalid purpose " + purpose,
            ),
            (
                (purpose == "test") == (row["kind"] == "test"),
                "test purpose requires test kind",
            ),
            (row["visibility"] in {"public", "caller"}, "invalid visibility"),
            (row["testonly"] in {"true", "false", "inherit"}, "invalid testonly"),
            (row["reason"] != "none", "require concrete reason"),
        ),
    )


def parse(doc: str) -> Contract:
    """Read the typed contract sections of a Bazel-evaluated docstring.

    Default outputs is required; a section without entries is omitted.
    """
    sections = _sections(doc)
    if "Default outputs" not in sections:
        raise ValueError("Default outputs: missing section")
    contract = Contract(
        *(
            _entries(title, sections[title]) if title in sections else ()
            for title in SECTIONS
        )
    )
    for row in contract.defaults:
        _check_default(row)
    for row in contract.companions:
        _check_companion(row)
    return contract


# ==== Evaluated comparison ====================================================


# The provider a kind's evaluated target must carry.
REQUIRED_PROVIDERS = {"library": "CcInfo", "toolchain": "ToolchainInfo"}


@dataclass(frozen=True)
class ConfiguredTarget:
    """Interfaces observed by evaluated analysis, not promises copied from the docs."""

    label: str
    files: int
    runfiles: int
    executable: bool
    providers: frozenset[str]
    groups: frozenset[str]


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


def has_provider(target: ConfiguredTarget, name: str) -> bool:
    """Whether a configured target returns a provider, by its name or its identity."""
    return any(key == name or key.endswith("%" + name) for key in target.providers)


def _test_errors(kind: str, test: bool) -> list[str]:
    """Compare a promised test with Bazel's own test classification."""
    promised = kind == "test"
    if promised == test:
        return []
    if promised:
        return ["promised test is not an evaluated Bazel test"]
    return ["undocumented evaluated test behavior"]


def _executable_errors(
    kind: str, target: ConfiguredTarget, shared_library: bool
) -> list[str]:
    """Compare promised running with the evaluated executable and its runfiles."""
    if kind in {"test", "executable"}:
        runs = target.executable and target.runfiles
        return [] if runs else ["missing promised executable or runfiles"]
    if target.executable and not shared_library:
        return ["undocumented executable behavior"]
    return []


def _content_errors(kind: str, target: ConfiguredTarget) -> list[str]:
    """Compare a kind's promised files and providers with the evaluated ones."""
    errors = []
    if kind in {"metadata", "toolchain"} and target.files:
        errors.append(kind + " must not produce default files")
    provider = REQUIRED_PROVIDERS.get(kind)
    if provider and not has_provider(target, provider):
        errors.append(f"{kind} lacks {provider}")
    return errors


def kind_errors(
    kind: str, target: ConfiguredTarget, *, test: bool, shared_library: bool = False
) -> list[str]:
    """Compare a documented default/companion/entrypoint kind with evaluated semantics.

    ``test`` is Bazel's own test classification. A ``cc_binary`` with ``linkshared``
    exposes RunfilesSupport, but it links rather than runs.
    """
    return [
        *_test_errors(kind, test),
        *_executable_errors(kind, target, shared_library),
        *_content_errors(kind, target),
    ]


def _difference(kind: str, expected: set[str], actual: set[str]) -> list[str]:
    return [
        f"missing documented {kind}: {name}" for name in sorted(expected - actual)
    ] + [f"undocumented {kind}: {name}" for name in sorted(actual - expected)]


def _cardinality_errors(cardinality: str, files: int) -> list[str]:
    """Compare a promised default output cardinality with the evaluated files."""
    if cardinality == "one" and files != 1:
        return ["default output cardinality must be one"]
    if cardinality == "none" and files:
        return ["default output cardinality must be none"]
    return []


def _group_errors(
    documented: set[str], target: ConfiguredTarget, forwarded_groups: bool
) -> list[str]:
    """Compare documented output groups with the evaluated public ones."""
    observed = {name for name in target.groups if not name.startswith("_")}
    if forwarded_groups:
        observed &= documented
    return _difference("group", documented, observed)


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
    defaults = active(contract.defaults, conditions)
    if len(defaults) != 1:
        return ["require exactly one active default output contract"]
    row = defaults[0]
    groups = {row["name"] for row in active(contract.groups, conditions)}
    promised = {row["name"] for row in active(contract.companions, conditions)}
    return [
        *_cardinality_errors(row["cardinality"], target.files),
        *kind_errors(row["kind"], target, test=test, shared_library=shared_library),
        *_group_errors(groups, target, forwarded_groups),
        *_difference("companion", promised, set(companions)),
    ]


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


# ==== Coverage ================================================================


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
    return DEFAULT_CONTRACT_LANE if module == RULESET.as_posix() else CONSUMER_MODULE_LANE


@dataclass(frozen=True)
class Api:
    """One extracted public export: its Stardoc kind, contract and defining identity."""

    kind: str
    contract: Contract
    origin: str


def is_repository_api(api: Api) -> bool:
    """Repository rules, module extensions and helper functions whose only output is repositories."""
    if api.kind in REPOSITORY_KINDS:
        return True
    return api.kind == "func_info" and [row["kind"] for row in api.contract.defaults] == [
        "repository"
    ]


def _promised_conditions(contract: Contract) -> set[str]:
    """The conditions a contract promises something under, other than always."""
    sections = (contract.defaults, contract.groups, contract.companions)
    return {row["availability"] for section in sections for row in section} - {"always"}


def _api_errors(
    identity: str,
    api: Api,
    cases: Mapping[str, dict],
    behavior: Mapping[str, list[str]],
) -> list[str]:
    """Require an export's configured cases, its conditions and its behavior test."""
    registered = [
        case for key, case in cases.items() if key.partition("#")[0] == identity
    ]
    errors = [] if registered else [f"{identity}: missing configured case"]
    covered = {
        condition for case in registered for condition in case.get("conditions", [])
    }
    errors.extend(
        f"{identity}: conditional availability {condition!r} has no configured case"
        for condition in sorted(_promised_conditions(api.contract) - covered)
    )
    if api.contract.companions and not behavior.get(identity):
        errors.append(f"{identity}: public companions need a registered behavior test")
    return errors


def _case_errors(key: str, case: dict, apis: Mapping[str, Api]) -> list[str]:
    """Check that a case names a known export, a lane and what it evaluates."""
    api = apis.get(key.partition("#")[0])
    if api is None:
        return [f"{key}: case refers to unknown API"]
    errors = []
    if case.get("lane", DEFAULT_CONTRACT_LANE) not in CONTRACT_LANES:
        errors.append(f"{key}: unknown required lane")
    if is_repository_api(api) != ("entrypoints" in case):
        errors.append(f"{key}: repository APIs, and only those, use entrypoint cases")
    elif "entrypoints" not in case and not case.get("target"):
        errors.append(f"{key}: missing evaluated target")
    return errors


def coverage_errors(
    apis: Mapping[str, Api],
    cases: Mapping[str, dict],
    behavior: Mapping[str, list[str]],
) -> list[str]:
    """Require every public export to own configured cases and companion tests."""
    errors = []
    for identity, api in apis.items():
        if api.kind != "provider_info":
            errors.extend(_api_errors(identity, api, cases, behavior))
    for key, case in cases.items():
        errors.extend(_case_errors(key, case, apis))
    errors.extend(
        f"{identity}: behavior test refers to unknown API"
        for identity in behavior
        if identity not in apis
    )
    return errors
