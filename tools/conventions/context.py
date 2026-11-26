"""Provide cached, read-only workspace, Starlark and Bazel facts to convention rules.

The Bazel tool that runs the loading queries is tools/conventions/bazel.py; this module
decodes their output.

Sections: Workspace, Starlark syntax, Bazel evidence, Source labels, Context.
"""

import io
import json
import os
import subprocess
import tokenize
import xml.etree.ElementTree as ET
from collections import defaultdict
from collections.abc import Iterable, Mapping
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path
from types import MappingProxyType
from typing import Protocol

from tools.conventions.environment import nested_tool_environment
from tools.conventions.layout import (
    DOCS,
    NON_CONSUMER_MODULES,
    project_directory,
    root_consumer,
)
from tools.setup.modules import is_registry_test_module

BUILD_FILES = frozenset({"BUILD", "BUILD.bazel"})


class EvidenceError(ValueError):
    """An evidence tool could not produce complete facts; the audit cannot pass."""


@dataclass(frozen=True)
class Location:
    path: str
    line: int


@dataclass(frozen=True)
class Module:
    path: Path
    builds: tuple[Path, ...]

    @cached_property
    def packages(self) -> tuple[str, ...]:
        """Package names relative to the module; its root package is ``""``."""
        return tuple(
            "" if package == "." else package
            for package in (
                build.parent.relative_to(self.path).as_posix() for build in self.builds
            )
        )


def run_tool(
    command: list[str], cwd: Path, variables: Mapping[str, str] | None = None
) -> str:
    """
    Return a tool's output, or fail the audit with its diagnostics. A nested Bazel gets the
    caller's variables, with the given ones.
    """
    try:
        environment = (
            {"env": nested_tool_environment(os.environ) | dict(variables or {})}
            if Path(command[0]).name == "bazel"
            else {}
        )
        return subprocess.run(
            command, cwd=cwd, capture_output=True, text=True, check=True, **environment
        ).stdout
    except subprocess.CalledProcessError as error:
        raise EvidenceError(
            f"{Path(command[0]).name} failed with exit status {error.returncode}\n"
            + (error.stderr or "")
        ) from error
    except OSError as error:
        raise EvidenceError(f"cannot run {command[0]}: {error}") from error


# ==== Workspace ===============================================================


def nearest(path: Path, roots: Iterable[Path]) -> Path | None:
    """The deepest root that contains path: a nested root owns its files, not the outer one."""
    owners = [root for root in roots if path.is_relative_to(root)]
    return max(owners, key=lambda root: len(root.parts)) if owners else None


@dataclass(frozen=True)
class StringLiteral:
    location: Location
    # Contents between the quotes; escapes stay undecoded.
    value: str


def string_literals(name: str, text: str) -> tuple[StringLiteral, ...]:
    """
    List string literals in Starlark source without evaluating it.

    Comments are skipped by the tokenizer. Contents keep their escapes undecoded,
    so Python's string semantics are never substituted for Starlark's.
    """
    try:
        tokens = tuple(tokenize.generate_tokens(io.StringIO(text).readline))
    except tokenize.TokenError as error:
        raise EvidenceError(f"{name}: cannot tokenize: {error}") from error
    literals = []
    for token in tokens:
        if token.type != tokenize.STRING:
            continue
        body = token.string.lstrip("rRbBuU")
        quotes = 3 if body[:3] in {'"""', "'''"} else 1
        literals.append(
            StringLiteral(Location(name, token.start[0]), body[quotes:-quotes])
        )
    return tuple(literals)


class Workspace:
    def __init__(self, root: Path, files: tuple[str, ...]) -> None:
        self.root = root
        # Git also lists tracked files that were deleted from the working tree.
        self.files = tuple(sorted({name for name in files if (root / name).is_file()}))
        # Present entries, including links to directories.
        self.entries = tuple(sorted(n for n in set(files) if os.path.lexists(root / n)))
        self._texts: dict[str, str] = {}
        self._strings: dict[str, tuple[StringLiteral, ...]] = {}

    @cached_property
    def file_set(self) -> frozenset[str]:
        return frozenset(self.files)

    @cached_property
    def documents(self) -> tuple[str, ...]:
        """Markdown under docs/ of the root or the ruleset and every README, not AGENTS.md."""
        return tuple(
            name
            for name in self.files
            if Path(name).suffix == ".md"
            and (name.startswith(DOCS) or Path(name).name.lower().startswith("readme"))
            and Path(name).name != "AGENTS.md"
        )

    @cached_property
    def configured(self) -> frozenset[Path]:
        """The directories with a project.godot of their own."""
        return frozenset(path.parent for path in self.godot_configurations)

    @cached_property
    def godot_configurations(self) -> tuple[Path, ...]:
        """Every ``project.godot`` file."""
        return tuple(
            Path(name) for name in self.files if Path(name).name == "project.godot"
        )

    def has_build(self, directory: Path) -> bool:
        """Whether a BUILD file makes the directory a package."""
        return any((directory / name).as_posix() in self.file_set for name in BUILD_FILES)

    def consumer_root(self, path: Path) -> Path | None:
        """
        The consumer that path belongs to: a consumer module, or one of the root module's
        consumer roots; none in the rest of the root module and in the ruleset module.
        """
        module = self.owner(path.as_posix())
        if module == Path("."):
            return root_consumer(path, self.module_paths)
        return None if module in NON_CONSUMER_MODULES else module

    def project(self, path: Path) -> Path | None:
        """The project at a fixed place of a consumer that path lies in, if any."""
        root = self.consumer_root(path)
        return None if root is None else project_directory(root, path, self.configured)

    @cached_property
    def projects(self) -> Mapping[Path, tuple[str, ...]]:
        """Map each project at a fixed place of a consumer to its files."""
        members: dict[Path, list[str]] = defaultdict(list)
        for name in self.files:
            project = self.project(Path(name))
            if project is not None:
                members[project].append(name)
        return MappingProxyType(
            {root: tuple(files) for root, files in sorted(members.items())}
        )

    def _roots(self, marker: str) -> tuple[Path, ...]:
        """Directories holding a file named marker, such as MODULE.bazel."""
        return tuple(
            Path(name).parent for name in self.files if Path(name).name == marker
        )

    @cached_property
    def module_paths(self) -> tuple[Path, ...]:
        return self._roots("MODULE.bazel")

    def owner(self, name: str) -> Path:
        """Return the nearest module directory, including nested standalone modules."""
        owner = nearest(Path(name), self.module_paths)
        if owner is None:
            raise EvidenceError(f"{name}: no owning MODULE.bazel")
        return owner

    @cached_property
    def repository_paths(self) -> tuple[Path, ...]:
        """Roots of repositories that are no module, such as local_repository fixtures."""
        return self._roots("REPO.bazel")

    @cached_property
    def loaded_modules(self) -> tuple[Module, ...]:
        """
        The modules whose Bazel evidence the check loads: every module but the registry test
        modules, which build only from a release archive (RG020).
        """
        return tuple(m for m in self.modules if not is_registry_test_module(m.path))

    @cached_property
    def modules(self) -> tuple[Module, ...]:
        """
        Resolve owned BUILD files against their nearest module without loading Bazel; a
        repository below a module that is no module itself belongs to none.
        """
        builds: dict[Path, list[Path]] = defaultdict(list)
        for name in self.files:
            if Path(name).name in BUILD_FILES:
                owner = self.owner(name)
                repository = nearest(Path(name), self.repository_paths)
                if repository is None or owner.is_relative_to(repository):
                    builds[owner].append(Path(name))
        return tuple(Module(path, tuple(files)) for path, files in sorted(builds.items()))

    def text(self, name: str) -> str:
        if name not in self._texts:
            try:
                self._texts[name] = (self.root / name).read_text()
            except (OSError, UnicodeDecodeError) as error:
                raise EvidenceError(f"{name}: cannot read: {error}") from error
        return self._texts[name]

    def strings(self, name: str) -> tuple[StringLiteral, ...]:
        """String literals of a Starlark file (BUILD, MODULE.bazel or .bzl)."""
        if name not in self._strings:
            self._strings[name] = string_literals(name, self.text(name))
        return self._strings[name]


# ==== Starlark syntax =========================================================


@dataclass(frozen=True)
class Call:
    location: Location
    kind: str
    attrs: frozenset[str]
    literal_name: str | None = None


# How a delimiter changes the nesting depth.
NESTING = {"(": 1, "[": 1, "{": 1, ")": -1, "]": -1, "}": -1}


def _is_name_argument(tokens: list[tokenize.TokenInfo], index: int) -> bool:
    """Whether the token at index starts a ``name = value`` argument with a value."""
    if index == 0 or tokens[index].string != "name":
        return False
    if tokens[index - 1].string not in {"(", ","}:
        return False
    return index + 3 < len(tokens) and tokens[index + 1].string == "="


def has_literal_name(source: str) -> bool:
    """
    Recognize one literal argument in Buildozer's already-parsed, formatted call.

    This only tokenizes delimiters and strings; it does not parse or evaluate
    Starlark. Buildozer supplies the decoded value, so Python's string semantics
    are never substituted for Starlark's.
    """
    try:
        tokens = [
            token
            for token in tokenize.generate_tokens(io.StringIO(source).readline)
            if token.type
            not in {
                tokenize.COMMENT,
                tokenize.NL,
                tokenize.NEWLINE,
                tokenize.ENDMARKER,
                tokenize.INDENT,
                tokenize.DEDENT,
            }
        ]
    except tokenize.TokenError as error:
        raise EvidenceError(f"cannot tokenize parsed call: {error}") from error
    depth = 0
    for index, token in enumerate(tokens):
        if depth == 1 and _is_name_argument(tokens, index):
            value, end = tokens[index + 2], tokens[index + 3]
            return value.type == tokenize.STRING and end.string in {",", ")"}
        depth += NESTING.get(token.string, 0)
    return False


class Buildozer:
    def __init__(self, root: Path, executable: Path) -> None:
        self.root = root
        self.executable = executable
        self._calls: dict[Module, tuple[Call, ...]] = {}
        self._names: dict[Module, str] = {}

    def module_name(self, module: Module) -> str:
        """The name the module declares in its MODULE.bazel."""
        if module not in self._names:
            output = run_tool(
                [
                    str(self.executable),
                    "-output_json",
                    "print name",
                    str(self.root / module.path / "MODULE.bazel") + ":%module",
                ],
                self.root,
            )
            records = json.loads(output).get("records", [])
            if len(records) != 1:
                raise EvidenceError(f"{module.path}/MODULE.bazel: expected one module()")
            self._names[module] = records[0]["fields"][0]["text"]
        return self._names[module]

    def calls(self, module: Module) -> tuple[Call, ...]:
        """Read syntax through the pinned parser; never evaluate Starlark with Python."""
        if module in self._calls:
            return self._calls[module]
        output = run_tool(
            [
                str(self.executable),
                "-output_json",
                "-respect_bazelignore=false",
                "print kind attrs path startline name rule",
                *[str(self.root / build.parent) + ":*" for build in module.builds],
            ],
            self.root,
        )
        calls = []
        for record in json.loads(output).get("records", []):
            kind, attrs, path, line, name, source = record["fields"]
            calls.append(
                Call(
                    Location(
                        Path(path["text"]).relative_to(self.root).as_posix(),
                        line["number"],
                    ),
                    kind["text"],
                    frozenset(attrs.get("list", {}).get("strings", [])),
                    name.get("text", "") if has_literal_name(source["text"]) else None,
                )
            )
        self._calls[module] = tuple(calls)
        return self._calls[module]


# ==== Bazel evidence ==========================================================


def location(root: Path, base: Path, value: str) -> Location:
    """Resolve a ``path:line:column`` value; relative paths start at base."""
    path, line, _column = value.rsplit(":", 2)
    source = Path(path)
    if not source.is_absolute():
        source = base / source
    source = source.resolve()
    name = (
        source.relative_to(root).as_posix()
        if source.is_relative_to(root)
        else str(source)
    )
    return Location(name, int(line))


def repository_root(root: Path, module: Module, rule: ET.Element) -> Path:
    """
    Return the root of the repository declaring a rule.

    Bazel reports generator_location relative to that repository, which differs from
    the querying module for targets of other modules.
    """
    build = Path(rule.attrib["location"].rsplit(":", 2)[0])
    if not build.is_absolute():
        build = root / module.path / build
    repository = build.parent
    for _ in Path(rule.attrib["name"].partition("//")[2].partition(":")[0]).parts:
        repository = repository.parent
    return repository


def generator_location(
    root: Path, module: Module, rule: ET.Element, origin: str | None
) -> Location | None:
    """The authored macro call, or None where Bazel names no file (another module's macro)."""
    if not origin:
        return None
    resolved = location(root, repository_root(root, module, rule), origin)
    return resolved if (root / resolved.path).is_file() else None


@dataclass(frozen=True)
class Target:
    label: str
    location: Location
    strings: Mapping[str, str]
    booleans: Mapping[str, bool]
    generator_location: Location | None
    kind: str
    labels: Mapping[str, str]
    label_lists: Mapping[str, tuple[str, ...]]
    label_keyed_strings: Mapping[str, Mapping[str, str]]
    outputs: tuple[str, ...]
    string_lists: Mapping[str, tuple[str, ...]]

    @property
    def is_test(self) -> bool:
        """Bazel requires test rule class names, and only those, to end in ``_test``."""
        return self.kind.endswith("_test")

    @property
    def origin(self) -> Location:
        """The authored call: a macro's caller, otherwise the rule's own location."""
        return self.generator_location or self.location

    def authored_inputs(self) -> frozenset[str]:
        """
        Labels in attributes the declaration chose.

        Implicit attributes come from the rule definition, and visibility grants
        access rather than consuming anything.
        """

        def authored(attribute: str) -> bool:
            return not attribute.startswith(("$", ":")) and attribute != "visibility"

        inputs = {value for name, value in self.labels.items() if authored(name)}
        # A label-keyed dictionary contributes its keys.
        for name, values in (
            *self.label_lists.items(),
            *self.label_keyed_strings.items(),
        ):
            if authored(name):
                inputs.update(values)
        return frozenset(inputs)


def _valued(rule: ET.Element, tag: str) -> dict[str, str]:
    """The values of a rule's attributes of one type that have a value, by name."""
    return {
        item.attrib["name"]: item.attrib["value"]
        for item in rule.findall(tag)
        if "value" in item.attrib
    }


def _lists(rule: ET.Element, tag: str) -> dict[str, tuple[str, ...]]:
    """The list attributes whose every element is of one type with a value, such as labels."""
    return {
        item.attrib["name"]: tuple(child.attrib["value"] for child in item)
        for item in rule.findall("list")
        if all(child.tag == tag and "value" in child.attrib for child in item)
    }


def _is_label_string_pair(pair: ET.Element) -> bool:
    """Whether a dictionary entry maps a label to a string, both with values."""
    if [child.tag for child in pair] != ["label", "string"]:
        return False
    return all("value" in child.attrib for child in pair)


def _label_keyed_strings(rule: ET.Element) -> dict[str, Mapping[str, str]]:
    """The dictionary attributes whose every entry maps a label to a string."""
    result = {}
    for item in rule.findall("dict"):
        pairs = item.findall("pair")
        if len(pairs) == len(item) and all(map(_is_label_string_pair, pairs)):
            result[item.attrib["name"]] = MappingProxyType(
                {pair[0].attrib["value"]: pair[1].attrib["value"] for pair in pairs}
            )
    return result


def _query_target(root: Path, module: Module, rule: ET.Element) -> Target:
    """Decode one rule of a loading query."""
    strings = {
        item.attrib["name"]: item.attrib.get("value", "")
        for item in rule.findall("string")
    }
    booleans = {name: value == "true" for name, value in _valued(rule, "boolean").items()}
    origin = strings.get("generator_location")
    return Target(
        label=rule.attrib["name"],
        location=location(root, root / module.path, rule.attrib["location"]),
        strings=MappingProxyType(strings),
        booleans=MappingProxyType(booleans),
        generator_location=generator_location(root, module, rule, origin),
        kind=rule.attrib["class"],
        labels=MappingProxyType(_valued(rule, "label")),
        label_lists=MappingProxyType(_lists(rule, "label")),
        label_keyed_strings=MappingProxyType(_label_keyed_strings(rule)),
        outputs=tuple(item.attrib["name"] for item in rule.findall("rule-output")),
        string_lists=MappingProxyType(_lists(rule, "string")),
    )


def query_targets(root: Path, module: Module, query: ET.Element) -> tuple[Target, ...]:
    """Decode loading metadata without naming policy, exemptions or diagnostics."""
    return tuple(_query_target(root, module, rule) for rule in query.findall("rule"))


@dataclass(frozen=True)
class SourceFile:
    label: str
    path: Path


@dataclass(frozen=True)
class GeneratedFile:
    label: str


Fact = Target | SourceFile | GeneratedFile


def query_files(root: Path, module: Module, query: ET.Element) -> dict[str, Fact]:
    """Decode the source and generated files of a loading query by label."""
    files: dict[str, Fact] = {}
    for element in query:
        label = element.attrib["name"]
        if element.tag == "source-file":
            value = location(root, root / module.path, element.attrib["location"])
            files[label] = SourceFile(label, (root / value.path).resolve())
        elif element.tag == "generated-file":
            files[label] = GeneratedFile(label)
    return files


# ==== Source labels ===========================================================


def main_label(path: Path) -> str:
    """The label of a file in the main repository, given relative to its root."""
    directory = path.parent.as_posix()
    return "//" + ("" if directory == "." else directory) + ":" + path.name


def _file_label(repository: str, relative: str) -> str:
    directory, _, basename = relative.rpartition("/")
    return repository + "//" + directory + ":" + basename


def _external_source_label(file: str) -> str:
    """The label of a source below Bazel's external directory."""
    external = (
        file.split("/external/", 1)[1]
        if "/external/" in file
        else file.removeprefix("external/")
    )
    repository, separator, relative = external.partition("/")
    if not separator:
        raise EvidenceError("unresolved evaluated external source: " + file)
    return _file_label("@@" + repository, relative)


def _main_path(file: str, main: Path) -> Path:
    """A source path relative to the main repository, absolute ones through links."""
    path = Path(file)
    if not path.is_absolute():
        return path
    resolved = path.resolve()
    if not resolved.is_relative_to(main.resolve()):
        raise EvidenceError("unresolved evaluated source repository: " + file)
    return resolved.relative_to(main.resolve())


def evaluated_source_label(root: Path, module: Module, file: str) -> str:
    """Turn an evaluated source frame into its repository-qualified Starlark label."""
    if file.startswith(("@", "//")) and "//" in file:
        repository, _, relative = file.partition("//")
        return file if ":" in relative else _file_label(repository, relative)
    path = Path(file)
    main = root / module.path
    if path.is_absolute() and path.is_relative_to(main):
        return main_label(path.relative_to(main))
    if "/external/" in file or file.startswith("external/"):
        return _external_source_label(file)
    return main_label(_main_path(file, main))


# ==== Context =================================================================


@dataclass(frozen=True)
class Declaration:
    call: Call
    targets: tuple[Target, ...]


class StarlarkTool(Protocol):
    def calls(self, module: Module) -> tuple[Call, ...]: ...

    def module_name(self, module: Module) -> str: ...


class BazelTool(Protocol):
    def rules(self, module: Module) -> tuple[Target, ...]: ...

    def inspect(self, module: Module, labels: tuple[str, ...]) -> Mapping[str, Fact]: ...

    def invocations(
        self, module: Module
    ) -> Mapping[str, tuple[tuple[str, str], ...]]: ...

    def dependent_tests(
        self, module: Module, labels: tuple[str, ...], excluded_tags: tuple[str, ...]
    ) -> frozenset[str]: ...


def join(calls: tuple[Call, ...], rules: tuple[Target, ...]) -> tuple[Declaration, ...]:
    """Attach each evaluated target to the one authored BUILD call it came from."""
    by_location: dict[Location, list[Call]] = defaultdict(list)
    for call in calls:
        by_location[call.location].append(call)
    targets: dict[Location, list[Target]] = defaultdict(list)
    for target in rules:
        origin = target.origin
        # Macro implementation calls are generated, not authored BUILD declarations.
        if Path(origin.path).name not in BUILD_FILES:
            continue
        candidates = by_location.get(origin, [])
        if len(candidates) != 1:
            raise EvidenceError(
                f"{origin.path}:{origin.line}: expected one parsed declaration, found {len(candidates)}"
            )
        targets[origin].append(target)
    return tuple(
        Declaration(by_location[origin][0], tuple(items))
        for origin, items in targets.items()
    )


class Context:
    def __init__(
        self, workspace: Workspace, starlark: StarlarkTool, bazel: BazelTool
    ) -> None:
        self.workspace = workspace
        self.starlark = starlark
        self.bazel = bazel
        self._declarations: dict[Module, tuple[Declaration, ...]] = {}

    @cached_property
    def local_repositories(self) -> frozenset[str]:
        """Names of the modules whose sources this workspace owns."""
        return frozenset(self.starlark.module_name(m) for m in self.workspace.modules)

    def is_local(self, label: str) -> bool:
        """Whether a label names a package of one of the workspace's own modules."""
        repository = label.partition("//")[0].lstrip("@")
        # A module's canonical repository name ends with "+"; extension repositories
        # contain further "+" separators and never match a module name.
        return repository == "" or repository.removesuffix("+") in self.local_repositories

    def sources(self, module: Module, labels: Iterable[str]) -> Mapping[str, Path]:
        """
        Map repository labels to the workspace path that defines them.

        A target maps to its authored call's BUILD file, a source file to its
        resolved path and a generated file to its place in the generating package.
        External labels and sources resolving outside the workspace are omitted:
        no workspace path owns them.
        """
        local = tuple(sorted({label for label in labels if self.is_local(label)}))
        facts = self.bazel.inspect(module, local) if local else {}
        root = self.workspace.root
        paths: dict[str, Path] = {}
        for label, fact in facts.items():
            if isinstance(fact, Target):
                paths[label] = Path(fact.origin.path)
            elif isinstance(fact, SourceFile) and fact.path.is_relative_to(root):
                paths[label] = fact.path.relative_to(root)
            elif isinstance(fact, GeneratedFile):
                paths[label] = self._package_path(module, label)
        return MappingProxyType(paths)

    @cached_property
    def _module_paths(self) -> Mapping[str, Path]:
        return MappingProxyType(
            {self.starlark.module_name(m): m.path for m in self.workspace.modules}
        )

    def _package_path(self, module: Module, label: str) -> Path:
        """Return the workspace path a local label names inside its package."""
        repository, _, rest = label.partition("//")
        name = repository.lstrip("@").removesuffix("+")
        package, _, target = rest.partition(":")
        base = module.path if not name else self._module_paths[name]
        return base / package / target

    def _frame_owner(self, module: Module, file: str, function: str) -> str:
        """The function of a frame's file: in the workspace if it owns the file."""
        label = evaluated_source_label(self.workspace.root, module, file)
        repository, _, relative = label.partition("//")
        name = repository.lstrip("@").removesuffix("+")
        base = module.path if not name else self._module_paths.get(name)
        if base is None:
            return label + "%" + function
        return main_label(base / relative.replace(":", "/")) + "%" + function

    def macro_owner(self, module: Module, declaration: Declaration) -> str | None:
        """Resolve the evaluated outer macro's physical source, never its name alone."""
        invocations = self.bazel.invocations(module)
        owners = set()
        for target in declaration.targets:
            frames = invocations.get(target.label, ())
            if frames:
                owners.add(self._frame_owner(module, *frames[0]))
            elif target.strings.get("generator_function"):
                raise EvidenceError(
                    f"{target.label}: missing evaluated macro instantiation ownership"
                )
        if len(owners) > 1:
            raise EvidenceError(
                f"{declaration.call.location}: ambiguous evaluated macro ownership: {sorted(owners)}"
            )
        return next(iter(owners), None)

    def declarations(self, module: Module) -> tuple[Declaration, ...]:
        """Join parsed source calls and evaluated targets, retaining macro fan-out."""
        if module not in self._declarations:
            # Load every module at once: a rule which needs one module's declarations visits
            # every module, and the Bazel tool loads each workspace's modules together.
            modules = [
                m for m in self.workspace.loaded_modules if m not in self._declarations
            ]
            if module not in modules:
                modules.append(module)
            with ThreadPoolExecutor() as pool:
                calls = {m: pool.submit(self.starlark.calls, m) for m in modules}
                rules = {m: pool.submit(self.bazel.rules, m) for m in modules}
                for m in modules:
                    self._declarations[m] = join(calls[m].result(), rules[m].result())
        return self._declarations[module]
