"""
Configure Godot's SCons build for a recipe and translate its graph into rules_cc targets.

SCons only evaluates upstream's feature logic. It runs no compiler, linker, source
generator or build cache; Bazel's actions do that work.

Sections: Engine version, Capture, Configurations, Pinning, Command line.
"""

import argparse
import ast
import hashlib
import importlib.util
import inspect
import json
import os
import re
import shlex
import sys
import tempfile
import textwrap
from collections import defaultdict
from collections.abc import (
    Callable,
    Collection,
    Iterable,
    Mapping,
    Sequence,
)
from pathlib import Path
from types import FunctionType
from typing import Any, cast

from tools.engine import build_profile
from tools.engine.compile_options import (
    deployment_target,
    engine_link_options,
    merge_swift_module_options,
    normalize_command,
    platform_compile_options,
    swift_module_options,
)
from tools.engine.custom_modules import shapes_graph
from tools.engine.generator_inputs import (
    include_closure,
    normalize_value,
    scalar_environment,
)
from tools.engine.lock import pinned_graph, read_lock
from tools.engine.module_graph import module_closure, module_dependencies
from tools.engine.recipe_options import (
    check_options,
    customizations,
    engine_renderers,
    has_renderer_switches,
    profile_options_digest,
    profile_renderers,
    renderer_options,
    requested_modules,
    require_consistent_profile,
    require_known_options,
    require_one_text_server,
    require_renderer_options_unset,
    with_renderer_modules,
)
from tools.engine.render import Variant, render, render_unpinned
from tools.engine.source_tree import SOURCE_SUFFIXES, digest_of, relative, write_json


def file_digest(path: Path) -> str:
    """Return the SHA-256 of a file's contents."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def file_digests(
    root: Path | None, by_content: Callable[[Path], bool] = lambda _path: True
) -> dict[str, str]:
    """
    Return each file below root by its relative path, with its SHA-256 where by_content
    accepts it and empty otherwise; nothing without a root.
    """
    if root is None:
        return {}
    return {
        path.relative_to(root).as_posix(): file_digest(path) if by_content(path) else ""
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


# ==== Engine version ==========================================================


_VERSION_FIELDS = ("major", "minor", "patch", "status")

_MINIMUM_VERSION = (4, 7, 2)


def _version_declarations(root: Path) -> dict[str, object]:
    """Return the values that the archive's version.py assigns to the version fields."""
    assignments = (
        (target.id, statement.value)
        for statement in ast.parse((root / "version.py").read_text()).body
        if isinstance(statement, ast.Assign)
        for target in statement.targets
        if isinstance(target, ast.Name) and target.id in _VERSION_FIELDS
    )
    return {name: ast.literal_eval(value) for name, value in assignments}


def _declared_version(values: Mapping[str, object]) -> tuple[int, int, int]:
    declared = tuple(values.get(key) for key in ("major", "minor", "patch"))
    if not all(type(value) is int and value >= 0 for value in declared):
        raise ValueError(
            "Godot source version.py must declare integer major, minor and patch values"
        )
    return cast("tuple[int, int, int]", declared)


def _declared_status(values: Mapping[str, object]) -> str:
    status = values.get("status", "stable")
    if not isinstance(status, str) or not re.fullmatch(
        r"stable|(?:dev|alpha|beta|rc)[0-9]*", status
    ):
        raise ValueError(f"Unrecognized Godot source version status: {status!r}")
    return status


def _is_unsupported_version(version: tuple[int, int, int], status: str) -> bool:
    """Return whether a version precedes the supported release, or is a pre-release of it."""
    return (
        version[0] != _MINIMUM_VERSION[0]
        or version < _MINIMUM_VERSION
        or (version == _MINIMUM_VERSION and status != "stable")
    )


def source_version(root: Path) -> str:
    """Validate the archive's actual version before evaluating its build graph."""
    values = _version_declarations(root)
    version = _declared_version(values)
    status = _declared_status(values)
    text = ".".join(map(str, version)) + ("" if status == "stable" else "-" + status)
    if _is_unsupported_version(version, status):
        raise ValueError(
            f"Godot {'.'.join(map(str, _MINIMUM_VERSION))} or newer Godot "
            f"{_MINIMUM_VERSION[0]} sources are required; archive contains {text}"
        )
    return text


def require_expected_version(actual: str, expected: str) -> None:
    """Reject sources whose version.py contradicts their descriptor."""
    if expected and actual != expected:
        raise ValueError(
            f"The source descriptor declares Godot {expected}, "
            f"but the extracted version.py is {actual}"
        )


def _module_selection(args: argparse.Namespace) -> dict[str, Any]:
    """The requested modules; the upstream defaults only when requested, so earlier digests hold."""
    selection: dict[str, Any] = {"modules": args.modules}
    if args.default_modules:
        selection["default_modules"] = True
    return selection


def _profile_input(args: argparse.Namespace) -> dict[str, str]:
    """The build profile's digest; nothing without one, so earlier digests hold."""
    digest = args.build_profile_digest
    return {"build_profile": digest} if digest else {}


def inputs_hash(args: argparse.Namespace) -> str:
    """
    Return the hash an unstamped source-built engine names in place of a Git commit.

    It covers the engine's declared inputs: the archive digest, the patches, the
    custom module trees and the configuration. Neither time nor host state enters
    it, so an unchanged engine keeps its hash and its cached actions. The CPU stays
    out, so the engines of one configuration for several Android ABIs name the same
    hash in their shared AAR.
    """
    inputs = {
        "source": args.source_sha256,
        "patches": [file_digest(path) for path in args.patch],
        "patch_strip": args.patch_strip,
        **_profile_input(args),
        "custom_modules": file_digests(args.custom_modules_root),
        "configuration": {
            "platform": args.platform,
            "build_target": args.build_target,
            **_module_selection(args),
            "options": sorted(args.options),
        },
    }
    # The length of a Git commit hash, which Godot shortens to 9 for display.
    return digest_of(inputs)[:40]


# Version fields the generated :revision target supplies at build time: the
# build name with the hash's origin, and the hash and time stamp in the Git
# commit's place, which a release tarball's .git/HEAD may name.
REVISION_FILES = {
    "version_info_builder": {"build": "_revision/build.txt"},
    "version_hash_builder": {
        "git_hash": "_revision/hash.txt",
        "git_timestamp": "_revision/timestamp.txt",
    },
}


def version_name(info: Mapping[str, object]) -> str:
    """
    Return an engine's version and status as its Android library manifest names them.

    The patch number is always present, as in the manifest of an official AAR.
    The build name and hash follow at build time, such as .custom-git.<hash>.
    """
    return "{major}.{minor}.{patch}.{status}{module_config}".format(**info)


# ==== Capture =================================================================


_OBJECT_SUFFIXES = (".o", ".os")

_CXX_SUFFIXES = (".cc", ".cpp", ".cxx", ".mm")


def _has_object_target(target_names: Iterable[str]) -> bool:
    return any(Path(name).suffix in _OBJECT_SUFFIXES for name in target_names)


def _is_swift_objects(sources: Sequence[Any], target_names: Sequence[str]) -> bool:
    """Return whether an executor compiles Swift sources into objects."""
    return (
        bool(sources)
        and all(Path(str(source)).suffix == ".swift" for source in sources)
        and _has_object_target(target_names)
    )


def _is_compiled_source(sources: Sequence[Any], target_names: Sequence[str]) -> bool:
    """Return whether an executor compiles one C-family or assembler source to an object."""
    return (
        len(sources) == 1
        and Path(str(sources[0])).suffix in SOURCE_SUFFIXES
        and _has_object_target(target_names)
    )


def _is_link_target(target_names: Iterable[str]) -> bool:
    return any(name.startswith(("bin/godot", "bin/libgodot")) for name in target_names)


def _compile_variable(suffix: str, shared: bool) -> str:
    """Return the SCons variable that holds the compile command for a source suffix."""
    if suffix in (".S", ".s"):
        return "$ASPPCOM" if suffix == ".S" else "$ASCOM"
    kind = "CXXCOM" if suffix in _CXX_SUFFIXES else "CCCOM"
    return ("$SH" if shared else "$") + kind


def _is_android_library(name: str) -> bool:
    return name.startswith("platform/android/java/lib/libs/") and name.endswith(
        ("/libgodot_android.so", "/libc++_shared.so")
    )


def _is_bazel_owned_output(platform: str, target_names: Sequence[str]) -> bool:
    """Return whether Bazel rules produce the targets, so no action replays them."""
    # rules_android owns AAR/JNI staging; do not replay SCons Move/Copy
    # actions into a mutable Gradle source tree.
    if platform == "android" and all(map(_is_android_library, target_names)):
        return True
    # rules_cc rules own archiving and retain every captured object.
    return all(Path(name).suffix in (".a", ".lib") for name in target_names)


def is_directory_action(actions: Sequence[Any]) -> bool:
    return (
        len(actions) == 1
        and getattr(getattr(actions[0], "execfunction", None), "__name__", "")
        == "MkdirFunc"
    )


def _generator_function(
    target_names: Sequence[str], actions: Sequence[Any]
) -> FunctionType:
    """Return the Python function that an executor's one action runs."""
    if len(actions) != 1 or not hasattr(actions[0], "execfunction"):
        raise ValueError(
            "Unsupported upstream Godot action for "
            + ", ".join(target_names)
            + ": "
            + ", ".join(type(action).__name__ for action in actions)
        )
    return actions[0].execfunction


def _generator_sources(
    root: Path, sources: Iterable[Any]
) -> tuple[list[dict[str, Any]], list[str]]:
    """Return a generator's source entries and the paths of those that are files."""
    entries: list[dict[str, Any]] = []
    files: list[str] = []
    for source in sources:
        if source.__class__.__module__ == "SCons.Node.Python":
            # Node-valued dictionaries used by custom module registration
            # are normalized to stable repository-relative paths.
            entries.append({"value": normalize_value(source.read(), root)})
        else:
            logical = relative(source, root)
            files.append(logical)
            entries.append({"path": logical})
    return entries, files


def _enabled_modules(
    link_environment: Any, selected_modules: Collection[str]
) -> list[str]:
    """Return the modules Godot enabled, which must include every selected module."""
    enabled = sorted(link_environment.module_list)
    missing = sorted(set(selected_modules) - set(enabled))
    if missing:
        raise ValueError(
            "Godot disabled requested modules for this configuration: "
            + ", ".join(missing)
        )
    require_one_text_server(enabled)
    return enabled


def _library_option(library: object) -> str | None:
    """Return the link option for a library SCons names, or None when it is no linked library."""
    if not isinstance(library, str):
        return None
    if library.startswith("-"):
        return library
    return None if library.endswith((".a", ".o", ".lib")) else "-l" + library


def _link_settings(
    link_environment: Any, platform: str, root: Path
) -> tuple[list[str], str]:
    """Return the engine's link options and its deployment target, from the link environment."""
    # SCons includes feature probes, but the action graph never retains host
    # compiler paths, SDK roots, arch flags, or an implicit SCons cache.
    linkopts = shlex.split(link_environment.subst("$LINKFLAGS $_LIBDIRFLAGS"))
    # Godot's Apple platforms put it in CCFLAGS; macOS also in LINKFLAGS.
    minimum_os = deployment_target(
        shlex.split(link_environment.subst("$CCFLAGS $LINKFLAGS"))
    )
    linkopts, _ = normalize_command(["linker", *linkopts], "", root)
    libraries = map(_library_option, link_environment.get("LIBS", []))
    linkopts.extend(option for option in libraries if option is not None)
    return engine_link_options(platform, linkopts), minimum_os


class _Capture:
    """The configured build graph, accumulated from SCons's recorded executors."""

    def __init__(self, platform: str, root: Path) -> None:
        self.platform = platform
        self.root = root
        self.groups: defaultdict[
            tuple[str, tuple[str, ...], tuple[str, ...]], list[str]
        ] = defaultdict(list)
        self.swift_sources: list[str] = []
        self.swift_options: dict[str, Any] | None = None
        self.generators: list[tuple[dict[str, Any], set[str]]] = []
        self.version = ""
        self.link_environment: Any = None
        self._emitted: set[tuple[str, ...]] = set()

    def add(self, executor: Any) -> None:
        """Record what an executor builds: an object, the link, a generator or nothing."""
        targets = executor.get_all_targets()
        sources = executor.get_all_sources()
        env = executor.get_build_env()
        actions = executor.get_action_list()
        target_names = self._claim(targets, actions)
        if target_names is None:
            return
        if _is_swift_objects(sources, target_names):
            self._add_swift_objects(targets, sources, env)
        # A source node may itself be produced by a source generator.
        elif _is_compiled_source(sources, target_names):
            self._add_compiled_source(targets, sources, env)
        elif _is_link_target(target_names):
            self.link_environment = env
        elif not _is_bazel_owned_output(self.platform, target_names):
            self._add_generator(target_names, sources, env, actions)

    def _claim(self, targets: Sequence[Any], actions: Sequence[Any]) -> list[str] | None:
        """Return the names of the targets that no action recorded before, or None."""
        if is_directory_action(actions):
            return None
        target_names = [relative(target, self.root) for target in targets]
        if not targets or tuple(target_names) in self._emitted:
            return None
        self._emitted.add(tuple(target_names))
        return target_names

    def _add_swift_objects(self, targets: Any, sources: Any, env: Any) -> None:
        self.swift_sources.extend(relative(source, self.root) for source in sources)
        if env.get("SWIFTCFLAGS"):
            command = env.subst_list("$SWIFTCFLAGS", target=targets, source=sources)[0]
            options = swift_module_options(list(map(str, command)), self.root)
            self.swift_options = merge_swift_module_options(
                self.swift_options, options, self.root
            )

    def _add_compiled_source(self, targets: Any, sources: Any, env: Any) -> None:
        source = relative(sources[0], self.root)
        suffix = Path(source).suffix
        language = "objc" if suffix in (".m", ".mm") else "cc"
        shared = targets[0].get_builder().get_name(env) == "SharedObject"
        variable = _compile_variable(suffix, shared)
        command = list(
            map(str, env.subst_list(variable, target=targets, source=sources)[0])
        )
        copts, includes = normalize_command(
            command,
            source,
            self.root,
            [
                env.get("APPLE_SDK_PATH"),
                env.get("IOS_SDK_PATH"),
                env.get("MACOS_SDK_PATH"),
            ],
        )
        copts = platform_compile_options(self.platform, copts)
        # Apple enables ARC globally, but it only applies to Objective-C.
        if language == "cc":
            copts = [option for option in copts if option != "-fobjc-arc"]
        self.groups[(language, tuple(copts), tuple(includes))].append(source)

    def _add_generator(
        self, target_names: list[str], sources: Any, env: Any, actions: Sequence[Any]
    ) -> None:
        function = _generator_function(target_names, actions)
        source_file = inspect.getsourcefile(function)
        if source_file is None:
            raise ValueError(f"Upstream Godot action {function.__name__} has no source")
        code_file = Path(source_file).resolve()
        # Postlink bundle/debug-sign actions belong to application packaging rules.
        if any(name.startswith("bin/") for name in target_names):
            return
        code = textwrap.dedent(inspect.getsource(function))
        spec: dict[str, Any] = {
            "code_file": relative(code_file, self.root),
            "function": function.__name__,
            "targets": target_names,
            "sources": [],
            "environment": scalar_environment(env, code, function.__globals__),
        }
        if code_file.suffix != ".py":
            spec["inline"] = code
        spec["sources"], files = _generator_sources(self.root, sources)
        dependencies = include_closure(self.root, files)
        if spec["function"] in REVISION_FILES:
            dependencies |= self._add_revision(spec)
        self.generators.append((spec, dependencies))

    def _add_revision(self, spec: dict[str, Any]) -> set[str]:
        """Name the files that a version generator's source supplies at build time."""
        files = REVISION_FILES[spec["function"]]
        spec["sources"][0]["files"] = files
        if spec["function"] == "version_info_builder":
            self.version = version_name(spec["sources"][0]["value"])
        return set(files.values())

    def graph(self, selected_modules: Collection[str]) -> dict[str, Any]:
        """Return the captured graph as plain data."""
        if not self.groups or self.link_environment is None:
            raise ValueError("Godot configure produced no engine compilation/link graph")
        if not self.version:
            raise ValueError(
                "Godot configure produced no version_generated.gen.h generator"
            )
        enabled = _enabled_modules(self.link_environment, selected_modules)
        linkopts, minimum_os = _link_settings(
            self.link_environment, self.platform, self.root
        )
        return {
            "groups": [
                [language, list(copts), list(includes), sources]
                for (language, copts, includes), sources in self.groups.items()
            ],
            "swift_sources": self.swift_sources,
            "swift_options": self.swift_options,
            # By their outputs, so recipes whose SCons visits generators in another order
            # share one list in a lock file.
            "generators": [
                {
                    "spec": build_profile.class_list_spec(spec),
                    "dependencies": sorted(dependencies),
                }
                for spec, dependencies in sorted(
                    self.generators, key=lambda item: item[0]["targets"]
                )
            ],
            "version": self.version,
            "modules": enabled,
            "linkopts": linkopts,
            "minimum_os": minimum_os,
        }


def collect(args: argparse.Namespace, executors: Iterable[Any]) -> dict[str, Any]:
    """
    Return the configured build graph of SCons's recorded executors as plain data.

    The graph names only paths relative to the source root and the flags Bazel replays,
    so it is the same on every host that configures the recipe, and a recipe's pin
    stores it. render() turns it into the repository's BUILD file.
    """
    capture = _Capture(args.platform, Path.cwd().resolve())
    for executor in executors:
        capture.add(executor)
    return capture.graph(args.selected_modules)


# ==== Configurations ==========================================================


def _add_environment_option(args: argparse.Namespace) -> None:
    """Pass an iOS recipe's device or simulator environment to Godot as its option."""
    if args.platform == "ios":
        if not args.environment:
            raise ValueError(
                "iOS recipes need an explicit device or simulator environment"
            )
        simulator = "yes" if args.environment == "simulator" else "no"
        args.options.append("simulator=" + simulator)
    elif args.environment:
        raise ValueError("The environment is only valid for iOS recipes")


def _add_renderer_options(args: argparse.Namespace, root: Path) -> None:
    """Add the upstream options of a recipe's renderers and the methods its engine runs."""
    args.engine_renderers = []
    if not args.renderers:
        return
    switches = has_renderer_switches(root)
    if args.build_profile:
        profiled = build_profile.read_profile(root / args.build_profile)
        args.renderers = profile_renderers(
            args.renderers, build_profile.build_options(profiled), args.platform, switches
        )
    derived = renderer_options(args.renderers, args.platform, switches)
    require_renderer_options_unset(derived, args.options)
    args.options = [*args.options, *derived]
    args.engine_renderers = engine_renderers(
        args.renderers, args.platform, args.environment, switches
    )


def _derive(args: argparse.Namespace, root: Path) -> None:
    """Add what a configuration derives from the recipe and its build profile."""
    args.options = list(args.requested.options)
    args.renderers = list(args.requested.renderers)
    args.modules = list(args.requested.modules)
    check_options(args.options)
    _add_renderer_options(args, root)
    args.modules = with_renderer_modules(args, args.module_graph)
    args.selected_modules = module_closure(
        args.modules, args.module_graph, editor=args.build_target == "editor"
    )
    # Before SCons for the modules a recipe names; Godot's defaults are checked after it.
    require_one_text_server(args.selected_modules)
    args.build_profile_digest = ""
    if args.build_profile:
        require_consistent_profile(root / args.build_profile, args.options)
        args.build_profile_digest = profile_options_digest(root / args.build_profile)
    args.customizations = customizations(args)
    _add_environment_option(args)
    args.inputs_hash = inputs_hash(args)


# ==== Pinning =================================================================


# The files whose code shapes a pinned graph: the capture and its translation.
# Rendering a graph, which render.py and include_graph.py do, changes no pin.
_PIN_TOOLS = (
    Path(__file__).resolve(),
    Path(inspect.getfile(normalize_command)).resolve(),
    Path(inspect.getfile(scalar_environment)).resolve(),
    Path(inspect.getfile(renderer_options)).resolve(),
    Path(inspect.getfile(module_closure)).resolve(),
    Path(inspect.getfile(relative)).resolve(),
    Path(inspect.getfile(build_profile)).resolve(),
    Path(inspect.getfile(shapes_graph)).resolve(),
)

# The version of a recipe pin's layout.
PIN_FORMAT = 1


def pin_inputs(args: argparse.Namespace, scons: Path) -> dict[str, Any]:
    """
    Return what a recipe's pin digest covers besides its build profile's options.

    Its runtime variants share it and differ only in their profiles, so a recipe computes
    the digests of its tools, patches and custom modules once.
    """
    tools = [file_digest(path) for path in [*_PIN_TOOLS, scons / "SCons" / "__init__.py"]]
    return {
        "format": PIN_FORMAT,
        "source": args.source_sha256,
        "patches": [file_digest(path) for path in args.patch],
        "patch_strip": args.patch_strip,
        "custom_modules": file_digests(args.custom_modules_root, shapes_graph),
        "configuration": {
            "platform": args.platform,
            "cpu": args.cpu,
            "build_target": args.build_target,
            **_module_selection(args),
            "options": sorted(args.options),
        },
        "build_name": args.build_name,
        "tools": tools,
    }


def pin_digest(
    args: argparse.Namespace, scons: Path, inputs: Mapping[str, Any] | None = None
) -> str:
    """
    Return the digest a recipe's pin records: what its configured graph depends on.

    It covers the archive digest, the patches, the custom modules' structure, the
    recipe's platform, CPU, build target, modules and options, its build profile's
    options, its build name, and the SCons release and rules_godot code that capture the
    graph. Host state is no input: a pin is valid on every host. inputs, pin_inputs()'s
    result, spares computing it again.
    """
    inputs = inputs if inputs is not None else pin_inputs(args, scons)
    return "sha256:" + digest_of({**inputs, **_profile_input(args)})


def write_pin(path: Path, digest: str, graph: Mapping[str, Any]) -> None:
    """Write one recipe's pin, the entry a lock file holds for it."""
    write_json(path, {"digest": digest, "graph": graph})


def variant_arguments(
    args: argparse.Namespace, root: Path, profile: str
) -> argparse.Namespace:
    """
    Return a recipe's arguments for its runtime variant of a registered runtime profile.

    The repository writes the variant's profile, the recipe's build options with the runtime
    profile's, to profile below the source root.
    """
    variant = argparse.Namespace(**vars(args))
    variant.build_profile = profile
    variant.registered_profile = True
    _derive(variant, root)
    return variant


_VARIANT_REASONS = {
    "missing": "has no pin for runtime profile {profile} of",
    "stale": "pins other sources, patches, modules, options or rules_godot code for "
    "runtime profile {profile} of",
}


def locked_variants(args: argparse.Namespace, root: Path, scons: Path) -> list[Variant]:
    """Return a pinned recipe's runtime variants, with the graphs of those with current pins."""
    pins = read_lock(args.lock)
    inputs = pin_inputs(args, scons)
    result = []
    for label, profile in args.runtime_profile:
        try:
            variant = variant_arguments(args, root, profile)
        except ValueError as error:
            result.append(Variant(label, args, None, f"{args.recipe}: {error}"))
            continue
        digest = pin_digest(variant, scons, inputs)
        status, graph = pinned_graph(pins, args.recipe, digest, label)
        reason = _VARIANT_REASONS.get(status, "").format(profile=label)
        error = args.unpinned_message.format(reason=reason) if graph is None else ""
        result.append(Variant(label, variant, graph, error))
    return result


def failure(output: str) -> str:
    """The exception a failed configuration's output reports, or else its last line."""
    lines = output.strip().splitlines() or ["the configuration failed"]
    errors = [line for line in lines if "Error: " in line]
    return (errors or lines)[-1].strip()


def captured_variants(args: argparse.Namespace, root: Path) -> list[Variant]:
    """
    Return a configured recipe's runtime variants, from the pins of their configurations.

    The repository configures each variant before the recipe, into <index>.json below
    args.variant_pins, or keeps its output in <index>.error where it could not.
    """
    result = []
    for index, (label, profile) in enumerate(args.runtime_profile):
        pin = args.variant_pins / f"{index}.json"
        if not pin.is_file():
            output = (args.variant_pins / f"{index}.error").read_text(errors="replace")
            error = f"The runtime profile {label} cannot apply to this recipe: "
            result.append(Variant(label, args, None, error + failure(output)))
            continue
        variant = variant_arguments(args, root, profile)
        graph = json.loads(pin.read_text())["graph"]
        result.append(Variant(label, variant, graph))
    return result


# ==== Command line ============================================================


def _argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True)
    parser.add_argument("--scons", required=True)
    parser.add_argument(
        "--platform", choices=("macos", "linuxbsd", "android", "ios"), required=True
    )
    parser.add_argument("--cpu", required=True)
    parser.add_argument(
        "--build-target",
        choices=("editor", "template_debug", "template_release"),
        default="template_release",
    )
    parser.add_argument("--environment", choices=("", "device", "simulator"), default="")
    parser.add_argument("--expected-version", default="")
    # Empty: the ruleset's default, see requested_modules.
    parser.add_argument("--modules", default="")
    # Start from the modules upstream enables by default, as Godot's official builds do.
    parser.add_argument("--default-modules", action="store_true")
    # The build profile's path below the source root, where the recipe repository holds it.
    parser.add_argument("--build-profile", default="")
    # Comma-separated rendering methods; empty keeps Godot's drivers and build_options'.
    parser.add_argument("--renderers", default="")
    parser.add_argument("--custom-modules", action="append", default=[])
    # A custom module below _custom_modules, where the recipe or its pin action prepared
    # it (custom_modules.py).
    parser.add_argument(
        "--custom-module-name", dest="custom_module_names", action="append", default=[]
    )
    parser.add_argument("--option", dest="options", action="append", default=[])
    parser.add_argument("--build-name", default="custom")
    parser.add_argument("--source-sha256", default="")
    parser.add_argument("--patch", type=Path, action="append", default=[])
    parser.add_argument("--patch-strip", type=int, default=1)
    parser.add_argument(
        "--generator-bzl",
        default="@autoload_rules_godot//godot/engine/private:generator.bzl",
    )
    parser.add_argument("--cc-repository", default="@rules_cc")
    parser.add_argument("--platforms-repository", default="@platforms")
    parser.add_argument("--apple-repository", default="@apple_support")
    parser.add_argument("--swift-repository", default="@rules_swift")
    # Render the recipe's graph from this lock file's entry instead of configuring; without
    # a current entry, the engine targets fail with this message, which names the reason.
    parser.add_argument("--lock", type=Path)
    parser.add_argument("--recipe", default="")
    parser.add_argument("--unpinned-message", default="")
    parser.add_argument(
        "--pin-bzl", default="@autoload_rules_godot//godot/engine/private:pin.bzl"
    )
    # The engine's registered runtime profiles with graph-shaping build options: each one's
    # label and the path of its variant's profile below the source root.
    parser.add_argument(
        "--runtime-profile",
        nargs=2,
        action="append",
        default=[],
        metavar=("LABEL", "PATH"),
    )
    # Where the repository configured the runtime variants of a recipe without a lock file.
    parser.add_argument("--variant-pins", type=Path)
    # The setting whose value, a build profile's label, selects a runtime variant.
    parser.add_argument(
        "--build-profile-label",
        default="@autoload_rules_godot//godot/private:build_profile_label",
    )
    # Configure and write the recipe's pin here instead of its BUILD file.
    parser.add_argument("--pin-output", type=Path)
    return parser


def _parse_arguments(argv: Sequence[str] | None) -> argparse.Namespace:
    args = _argument_parser().parse_args(argv)
    if not re.fullmatch(r"[A-Za-z0-9_]+", args.build_name):
        raise ValueError(
            f"build_name must be letters, digits and underscores: {args.build_name!r}"
        )
    args.modules = requested_modules(args.modules, args.default_modules)
    return args


def _add_custom_modules(args: argparse.Namespace, root: Path) -> None:
    """Name the directory of the custom modules below _custom_modules in the arguments."""
    args.custom_modules_root = (
        root / "_custom_modules" if args.custom_module_names else None
    )
    if args.custom_module_names:
        args.custom_modules.append("_custom_modules")


def _prepare(args: argparse.Namespace, root: Path) -> None:
    """Check the source and add the custom modules: what every configuration of a recipe shares."""
    args.version = source_version(root)
    require_expected_version(args.version, args.expected_version)
    (root / "engine_manifest.json").unlink(missing_ok=True)
    _add_custom_modules(args, root)
    args.module_graph = module_dependencies(
        root, [root / path for path in args.custom_modules]
    )
    # What the recipe requests, before its build profile and renderers add to it.
    args.requested = argparse.Namespace(
        options=list(args.options),
        renderers=[method for method in args.renderers.split(",") if method],
        modules=list(args.modules),
    )
    args.registered_profile = False
    args.runtime_profiles = [label for label, _ in args.runtime_profile]


def _complete_arguments(args: argparse.Namespace, root: Path) -> None:
    """Validate the recipe and add what it derives from the source: version, modules, hash."""
    _prepare(args, root)
    _derive(args, root)


def _install_capture(
    args: argparse.Namespace, root: Path, scons: Path, digest: str
) -> Callable[[], None]:
    """
    Make SCons record its executors and, after configuration, write the pin or the BUILD file.

    Return SCons's main function.
    """
    sys.path.insert(0, str(scons))
    import SCons.Executor
    import SCons.Script.Main
    import SCons.Variables

    executors: list[Any] = []
    original = SCons.Executor.Executor.__init__
    # The names of Godot's options, its modules' among them, as SConstruct declares them.
    options: set[str] = set()
    original_update = SCons.Variables.Variables.Update

    def record(executor: Any, *values: Any, **kwargs: Any) -> None:
        original(executor, *values, **kwargs)
        executors.append(executor)

    def update(variables: Any, *values: Any, **kwargs: Any) -> None:
        options.update(variables.keys())
        original_update(variables, *values, **kwargs)

    def finish(*_args: Any) -> None:
        if args.build_profile:
            require_known_options(root / args.build_profile, options)
        captured = collect(args, executors)
        if args.pin_output:
            write_pin(args.pin_output, digest, captured)
        else:
            render(args, captured, root, captured_variants(args, root))

    SCons.Executor.Executor.__init__ = record
    SCons.Variables.Variables.Update = update
    SCons.Script.Main._build_targets = finish
    return SCons.Script.Main.main


def load_detect(root: Path, platform: str) -> Any:
    """Load a platform's detect.py; the source root must be on sys.path for its imports."""
    path = root / "platform" / platform / "detect.py"
    spec = importlib.util.spec_from_file_location("_godot_detect", path)
    if spec is None or spec.loader is None:
        raise ValueError(f"Cannot load {path}")
    detect = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(detect)
    return detect


def require_host_platform(root: Path, platform: str) -> None:
    """
    Reject a recipe whose platform this host cannot configure.

    SConstruct offers only the platforms whose detect.py can_build() accepts the host, such
    as linuxbsd on a non-macOS POSIX host, and otherwise prints its platform list. A
    registered execution or target platform can still select such a recipe. The source
    root must be on sys.path, since detect.py imports upstream's build helpers.
    """
    if not load_detect(root, platform).can_build():
        raise ValueError(
            f"Godot's platform/{platform}/detect.py rejects this host ({sys.platform}) "
            "or its environment, such as a missing SDK or cross toolchain; build without "
            "the execution or target platform that selects this recipe here, or "
            "configure it on a host that Godot accepts"
        )


# Stand-ins for the host tools Godot's Linux detect.py probes. Every package query fails, so a
# configuration reads none of the host's packages, which compile actions would not declare:
# Godot's bundled libraries and dynamically loaded system libraries only. Without
# wayland-scanner, whose generators are shell commands, Godot builds without Wayland.
_LINUX_PROBES = {
    "pkg-config": '#!/bin/sh\nif [ "$1" = "--version" ]; then echo 0.29.2; exit 0; fi\nexit 1\n',
    "wayland-scanner": "#!/bin/sh\nexit 1\n",
}


def stand_in_host(root: Path, platform: str, directory: Path) -> None:
    """
    Replace the host state Godot's configuration probes, so it is the same on every host.

    Linux probes tools on PATH; Android only checks that the SDK and Godot's NDK version
    exist and names their compilers, which Bazel's toolchain replaces.
    """
    if platform == "linuxbsd":
        for name, script in _LINUX_PROBES.items():
            tool = directory / name
            tool.write_text(script)
            tool.chmod(0o755)
        os.environ["PATH"] = f"{directory}{os.pathsep}{os.environ.get('PATH', '')}"
    elif platform == "android":
        sdk = directory / "android_sdk"
        (sdk / "ndk" / load_detect(root, platform).get_ndk_version()).mkdir(parents=True)
        os.environ["ANDROID_HOME"] = str(sdk)
        os.environ.pop("ANDROID_SDK_ROOT", None)


def _scons_arguments(args: argparse.Namespace) -> list[str]:
    """Return the command line that configures Godot's build for the recipe."""
    arguments = [
        "scons",
        "--quiet",
        "--no-cache",
        f"platform={args.platform}",
        f"arch={args.cpu}",
        f"target={args.build_target}",
        "modules_enabled_by_default=" + ("yes" if args.default_modules else "no"),
        "scu_build=no",
        "generate_bundle=no",
        "debug_symbols=no",
        "separate_debug_symbols=no",
        "lto=none",
        "use_static_cpp=no",
        *args.options,
        *(f"module_{module}_enabled=yes" for module in args.selected_modules),
    ]
    if args.platform == "android":
        arguments.append("generate_android_binaries=no")
    if args.custom_modules:
        arguments.append("custom_modules=" + ",".join(args.custom_modules))
    if args.build_profile:
        arguments.append(f"build_profile={args.build_profile}")
    return arguments


def _configure(
    args: argparse.Namespace, root: Path, scons_main: Callable[[], None]
) -> None:
    """Run SCons's configuration of Godot's build for the recipe."""
    with tempfile.TemporaryDirectory(prefix="godot_configure_") as stand_ins:
        stand_in_host(root, args.platform, Path(stand_ins))
        require_host_platform(root, args.platform)
        # Upstream reads the build name from the environment; the repository's
        # build_name attribute is its only source.
        os.environ["BUILD_NAME"] = args.build_name
        sys.argv = _scons_arguments(args)
        # SCons reports status 2 if no Taskmaster ran, since this deliberately stops
        # after configuration. Success is an atomically written BUILD + manifest, or the pin.
        marker = args.pin_output or root / "engine_manifest.json"
        try:
            scons_main()
        except SystemExit as error:
            if error.code not in (None, 0, 2) or not marker.is_file():
                raise


def main(argv: Sequence[str] | None = None) -> None:
    args = _parse_arguments(argv)
    root = Path(args.source).resolve()
    scons = Path(args.scons).resolve()
    _complete_arguments(args, root)
    digest = pin_digest(args, scons)
    if args.lock:
        status, pinned = pinned_graph(read_lock(args.lock), args.recipe, digest)
        if pinned is None:
            render_unpinned(args, status, root)
        else:
            render(args, pinned, root, locked_variants(args, root, scons))
        return
    if args.pin_output:
        args.pin_output = args.pin_output.resolve()
    scons_main = _install_capture(args, root, scons, digest)
    os.chdir(root)
    sys.path.insert(0, str(root))
    _configure(args, root, scons_main)


if __name__ == "__main__":
    main()
