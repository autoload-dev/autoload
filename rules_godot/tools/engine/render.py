"""
Render a configured engine graph as the BUILD file of its recipe repository.

The graph comes from Godot's SCons configuration, now or from a recipe's pin. Rendering
reads the extracted tree, but the graph does not depend on it, so a recipe's pin does
not cover this module: changing how a graph renders keeps every pin.
"""

import argparse
from collections.abc import Collection, Container, Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any, NamedTuple

try:
    from . import build_profile, define_analysis
    from .include_graph import (
        CompileGroup,
        Generated,
        components,
        include_graph,
        reached_directories,
    )
    from .source_tree import SOURCE_SUFFIXES, relative, write_json
except ImportError:
    import build_profile
    import define_analysis
    from include_graph import (
        CompileGroup,
        Generated,
        components,
        include_graph,
        reached_directories,
    )
    from source_tree import SOURCE_SUFFIXES, relative, write_json


def target_constraints(args: argparse.Namespace) -> list[str]:
    operating_system = {
        "macos": "macos",
        "linuxbsd": "linux",
        "android": "android",
        "ios": "ios",
    }[args.platform]
    cpus = {
        "arm64": "aarch64",
        "arm32": "arm",
        "x86_32": "x86_32",
        "x86_64": "x86_64",
        "rv64": "riscv64",
    }
    if args.cpu not in cpus:
        raise ValueError(f"No Bazel CPU constraint mapping for SCons arch={args.cpu}")
    result = [
        f"{args.platforms_repository}//os:{operating_system}",
        f"{args.platforms_repository}//cpu:{cpus[args.cpu]}",
    ]
    if args.platform == "ios":
        result.append(f"{args.apple_repository}//constraints:" + args.environment)
    return result


def source_build_facts(args: argparse.Namespace) -> dict[str, str]:
    """Describe the configured source graph independently of a consumer's build request."""
    build_target = args.build_target
    if build_target not in {"editor", "template_debug", "template_release"}:
        raise ValueError(
            f"Unknown build target {build_target}; "
            "expected editor, template_debug or template_release"
        )
    return {
        "canonical_version": args.version,
        "platform": "linux" if args.platform == "linuxbsd" else args.platform,
        "cpu": args.cpu,
        "environment": args.environment,
        "role": "editor" if build_target == "editor" else "runtime",
        "variant": ""
        if build_target == "editor"
        else build_target.removeprefix("template_"),
    }


def header_ancestors(generated_headers: Iterable[str]) -> frozenset[Path]:
    """Every directory that contains a generated header, directly or below it."""
    directories = {Path(header).parent for header in generated_headers}
    return frozenset(
        ancestor
        for directory in directories
        for ancestor in (directory, *directory.parents)
    )


def object_groups(
    groups: Mapping[tuple[str, tuple[str, ...], tuple[str, ...]], Iterable[str]],
    generated_headers: Iterable[str],
    generated_sources: Container[str],
) -> list[tuple[str, tuple[str, ...], tuple[str, ...], list[str]]]:
    """
    Split compile groups so each source sees only its own generated include directories.

    Generated headers of different directories share basenames, such as each platform's
    export/logo_svg.gen.h; a library-wide include path would resolve them to one.
    """
    ancestors = header_ancestors(generated_headers)
    result: dict[tuple[str, tuple[str, ...], tuple[str, ...]], list[str]] = {}
    for (language, copts, includes), sources in sorted(groups.items()):
        for source in sorted(set(sources)):
            parent = Path(source).parent
            directories = (
                [str(parent)]
                if source in generated_sources or parent in ancestors
                else []
            )
            key = (language, copts, tuple(dict.fromkeys([*includes, *directories])))
            result.setdefault(key, []).append(source)
    return [(*key, sources) for key, sources in sorted(result.items())]


def engine_targets(platform: str) -> list[str]:
    """The public targets render() declares for a platform's engine."""
    return (
        ["engine_library", "libgodot_android.so", "godot"]
        if platform == "android"
        else (["engine_library"] if platform == "ios" else ["engine_library", "godot"])
    )


_UNPINNED_REASONS = {
    "missing": "has no pin for",
    "stale": "pins other sources, patches, modules, options or rules_godot code for",
}


def render_unpinned(args: argparse.Namespace, status: str, root: Path) -> None:
    """Write a BUILD file whose engine targets fail with the repin command."""
    message = args.unpinned_message.format(reason=_UNPINNED_REASONS[status])
    lines = [
        f'load("{args.pin_bzl}", "godot_unpinned_recipe")',
        'package(default_visibility = ["//visibility:public"])',
        *(
            f"godot_unpinned_recipe(name = {name!r}, message = {message!r})"
            for name in engine_targets(args.platform)
        ),
    ]
    (root / "BUILD.bazel").write_text("\n".join(lines) + "\n")


def _header_rules(args: argparse.Namespace, uses_swift: bool) -> list[str]:
    """Return the loads, package defaults and revision target that open the BUILD file."""
    lines = [
        "# Generated from Godot SCons; do not edit.",
        f'load("{args.cc_repository}//cc:cc_library.bzl", "cc_library")',
        f'load("{args.cc_repository}//cc:cc_binary.bzl", "cc_binary")',
        f'load("{args.cc_repository}//cc:objc_library.bzl", "objc_library")',
    ]
    if uses_swift:
        lines.append(
            f'load("{args.swift_repository}//swift:swift_library.bzl", "swift_library")'
        )
    lines += [
        f'load("{args.generator_bzl}", "godot_source_generator", "godot_source_headers", "godot_source_library", "godot_source_binary", "godot_source_revision", "godot_define_analysis", "godot_source_defines")',
        'package(default_visibility = ["//visibility:public"])',
        'exports_files(["engine_manifest.json"])',
        f"godot_source_revision(name = 'revision', visibility = ['//visibility:private'], build_name = {args.build_name!r}, inputs_hash = {args.inputs_hash!r}, build = '_revision/build.txt', hash = '_revision/hash.txt', timestamp = '_revision/timestamp.txt')",
        # The source root's include directory, which every compile action searches.
        "cc_library(name = '_root', visibility = ['//visibility:private'], includes = ['.'])",
    ]
    return lines


def _generator_rules(
    root: Path, generators: Sequence[tuple[dict[str, Any], set[str]]]
) -> tuple[list[str], list[str]]:
    """
    Write each generator's specification and return its rules and its generated headers.

    A generator's inputs are its dependencies and the Python files of the source tree.
    """
    python_files = sorted(
        relative(path, root)
        for path in root.rglob("*.py")
        if "_scons" not in path.parts and "_bazel_generators" not in path.parts
    )
    lines: list[str] = []
    generated_headers: list[str] = []
    for index, (spec, dependencies) in enumerate(generators):
        name = f"_generate_{index:04d}"
        manifest = f"_bazel_generators/{name}.json"
        write_json(root / manifest, spec)
        inputs = {source: source for source in sorted(dependencies | set(python_files))}
        # A script's SCsub is needed for inspection provenance, but its captured
        # function is executed alone by tools/engine/generator.py.
        inputs[spec["code_file"]] = spec["code_file"]
        attributes = {
            "name": name,
            "spec": manifest,
            "inputs": inputs,
            "outs": spec["targets"],
        }
        lines.append(_multiline_rule("godot_source_generator", attributes))
        generated_headers.extend(
            name for name in spec["targets"] if Path(name).suffix not in SOURCE_SUFFIXES
        )
    return lines, generated_headers


def generated_files(
    root: Path, specs: Iterable[Mapping[str, Any]]
) -> dict[str, Generated]:
    """Return each generated file with its generator's code, inputs and outputs."""
    files: dict[str, Generated] = {}
    for spec in specs:
        code = spec.get("inline") or (root / spec["code_file"]).read_text()
        inputs = tuple(entry["path"] for entry in spec["sources"] if "path" in entry)
        outputs = tuple(spec["targets"])
        files.update((target, Generated(code, inputs, outputs)) for target in outputs)
    return files


def include_rules(
    graph: Mapping[str, Collection[str]],
) -> tuple[list[str], dict[str, str]]:
    """
    Return a header target per set of files that include each other, and each file's target.

    Each target depends on the targets of the files its files include, so a compile
    action's inputs are what its source reaches.
    """
    included = {name for names in graph.values() for name in names}
    lines: list[str] = []
    targets: dict[str, str] = {}
    for component in components(graph):
        if included.isdisjoint(component):
            continue
        label = ":_includes/" + component[0]
        targets.update((file, label) for file in component)
        deps = sorted(
            {targets[include] for file in component for include in graph[file]} - {label}
        )
        lines.append(
            f"godot_source_headers(name = {label[1:]!r}, hdrs = {component!r}, deps = {deps!r})"
        )
    return lines, targets


def _source_deps(
    graph: Mapping[str, Collection[str]], targets: Mapping[str, str], source: str
) -> list[str]:
    """The source root's include directory and the header targets of a source's includes."""
    return [":_root", *sorted({targets[name] for name in graph[source]})]


def _multiline_rule(rule: str, attributes: Mapping[str, object]) -> str:
    return (
        rule
        + "(\n"
        + "".join(f"    {key} = {value!r},\n" for key, value in attributes.items())
        + ")"
    )


def object_library_name(source: str, group: int, taken: Container[str]) -> str:
    """
    Return the name of a source's library, which objc_library allows no slash in.

    A source that another compile group also compiles, or whose name another source's
    flattened path takes, adds its group's index.
    """
    name = "_objects__" + source.replace("/", "__")
    return name if name not in taken else f"{name}__{group}"


def constants(
    prefix: str, values: Mapping[str, Sequence[str]]
) -> tuple[list[str], dict[str, str]]:
    """
    Return a constant per distinct list of the sources' values and each source's constant.

    The constants of a compile group share its prefix, such as _INCLUDES_3, and count up.
    """
    lines: list[str] = []
    names: dict[tuple[str, ...], str] = {}
    by_source: dict[str, str] = {}
    for source, value in values.items():
        key = tuple(value)
        if key not in names:
            names[key] = f"{prefix}_{len(names)}"
            lines.append(f"{names[key]} = {list(key)!r}")
        by_source[source] = names[key]
    return lines, by_source


def _group_constants(index: int, language: str, copts: Sequence[str]) -> list[str]:
    """A group's options; C and C++ groups keep their -D and -U options apart."""
    if language == "objc":
        return [f"_COPTS_{index} = {list(copts)!r}"]
    return [
        f"_COPTS_{index} = {[c for c in copts if not define_analysis.is_definition(c)]!r}",
        f"_DEFINES_{index} = {[c for c in copts if define_analysis.is_definition(c)]!r}",
    ]


class _Library(NamedTuple):
    """A source's library and the options it compiles with."""

    group: int
    language: str
    source: str
    name: str
    includes: str
    deps: list[str]
    local_defines: list[str]


def _library_rules(
    library: _Library,
) -> tuple[list[str], define_analysis.AnalyzedSource | None]:
    """A source's library rule, with its define analysis unless it is Objective-C."""
    common = f"name = {library.name!r}, visibility = ['//visibility:private'], "
    rest = f"includes = {library.includes}, deps = {library.deps!r}, alwayslink = True)"
    if library.language == "objc":
        defines = f"local_defines = {library.local_defines!r}, " * bool(
            library.local_defines
        )
        return [
            (
                f"objc_library({common}srcs = {[library.source]!r}, "
                f"copts = _COPTS_{library.group}, {defines}{rest}"
            )
        ], None
    analyzed = define_analysis.AnalyzedSource(library.group, library.source, library.name)
    header = define_analysis.header(library.name)
    return [
        define_analysis.defines_rule(
            analyzed, library.includes, library.local_defines, library.deps
        ),
        (
            f"cc_library({common}srcs = {[library.source, header]!r}, "
            f"copts = _COPTS_{library.group} + ['-include', {header!r}], {rest}"
        ),
    ], analyzed


def object_rules(
    groups: Sequence[tuple[str, tuple[str, ...], tuple[str, ...], list[str]]],
    graph: Mapping[str, Collection[str]],
    targets: Mapping[str, str],
    profile_users: Container[str],
) -> tuple[list[str], list[str]]:
    """
    Return a library rule per source and the labels of those libraries.

    A library is named after its source, so its object keeps its path, and its cache key,
    when other compile groups of the engine change. Sources that register classes see
    the build profile. A source compiles with only the include directories that hold a
    file it reaches. C and C++ sources take their macro definitions from the define
    analysis; Objective-C sources, which import implicit modules, keep their -D options.
    """
    reached = reached_directories(
        graph, {directory for _, _, includes, _ in groups for directory in includes}
    )
    lines: list[str] = []
    labels: list[str] = []
    names: set[str] = set()
    analyzed: list[define_analysis.AnalyzedSource] = []
    for index, (language, copts, includes, sources) in enumerate(groups):
        lines += _group_constants(index, language, copts)
        include_lines, source_includes = constants(
            f"_INCLUDES_{index}",
            {source: [d for d in includes if d in reached[source]] for source in sources},
        )
        lines += include_lines
        for source in sources:
            name = object_library_name(source, index, names)
            names.add(name)
            labels.append(":" + name)
            library_lines, source_analysis = _library_rules(
                _Library(
                    index,
                    language,
                    source,
                    name,
                    source_includes[source],
                    _source_deps(graph, targets, source),
                    [build_profile.DEFINE] if source in profile_users else [],
                )
            )
            lines += library_lines
            if source_analysis:
                analyzed.append(source_analysis)
    return lines + define_analysis.analysis_rules(analyzed), labels


_DEFAULT_SWIFT_OPTIONS: dict[str, Any] = {
    "module_name": "godot_swift_module",
    "bridging_header": "drivers/apple_embedded/bridging_header_apple_embedded.h",
    "generated_header": None,
    "copts": ["-swift-version", "6", "-cxx-interoperability-mode=default"],
}


def _swift_rule(
    swift_sources: Iterable[str], options: Mapping[str, Any], deps: list[str]
) -> str:
    attributes: dict[str, object] = {
        "name": "_swift",
        "visibility": ["//visibility:private"],
        "srcs": sorted(set(swift_sources)),
        "module_name": options["module_name"],
        "copts": options["copts"]
        + ["-import-objc-header", f"$(location {options['bridging_header']})"],
        "swiftc_inputs": [options["bridging_header"]],
        "deps": deps,
        "generates_header": bool(options["generated_header"]),
        "alwayslink": True,
    }
    if options["generated_header"]:
        attributes["generated_header_name"] = Path(options["generated_header"]).name
    return _multiline_rule("swift_library", attributes)


# Upstream's combined static archive cannot carry application framework dependencies;
# the iOS engine library represents them with Bazel's built-in Objective-C providers.
_IOS_FRAMEWORKS = [
    "ARKit",
    "AVFoundation",
    "AudioToolbox",
    "CoreAudio",
    "CoreGraphics",
    "CoreHaptics",
    "CoreMedia",
    "CoreMotion",
    "CoreText",
    "CoreVideo",
    "Foundation",
    "GameController",
    "Metal",
    "OpenGLES",
    "QuartzCore",
    "Security",
    "SystemConfiguration",
    "UIKit",
    "UniformTypeIdentifiers",
]


def _source_rule(
    args: argparse.Namespace, graph: Mapping[str, Any], name: str, library: str
) -> str:
    """Return the rule that publishes a built library with the engine's provenance."""
    facts = source_build_facts(args)
    metadata_arguments = ", ".join(f"{key} = {value!r}" for key, value in facts.items())
    digest = "sha256:" + args.source_sha256 if args.source_sha256 else ""
    rule = (
        "godot_source_library"
        if args.platform in {"android", "ios"}
        else "godot_source_binary"
    )
    renderers = (
        f", renderers = {args.engine_renderers!r}, declares_renderers = True"
        if args.renderers
        else ""
    )
    return f"{rule}(name = {name!r}, deps = [{library!r}], version = {graph['version']!r}, build = '_revision/build.txt', hash = '_revision/hash.txt', digest = {digest!r}, customizations = {args.customizations!r}, minimum_os = {graph['minimum_os']!r}, {metadata_arguments}{renderers})"


def _engine_rules(
    args: argparse.Namespace, graph: Mapping[str, Any], dependencies: list[str]
) -> list[str]:
    """Return the rules of the platform's engine targets."""
    # Android's libgodot is a shared library. iOS consumers link engine_library
    # through rules_apple; cc_binary is the desktop executable/editor.
    compatibility = target_constraints(args)
    linkopts = graph["linkopts"]
    if args.platform == "ios":
        return [
            f"objc_library(name = '_engine_library', visibility = ['//visibility:private'], deps = {dependencies!r}, linkopts = {linkopts!r}, sdk_frameworks = {_IOS_FRAMEWORKS!r}, sdk_dylibs = ['c++', 'z', 'iconv'], target_compatible_with = {compatibility!r})",
            _source_rule(args, graph, "engine_library", ":_engine_library"),
        ]
    library = f"cc_library(name = 'engine_library', deps = {dependencies!r}, linkopts = {linkopts!r}, target_compatible_with = {compatibility!r})"
    if args.platform == "android":
        return [
            library,
            f"cc_binary(name = 'libgodot_android.so', deps = [':engine_library'], linkstatic = True, linkshared = True, target_compatible_with = {compatibility!r})",
            _source_rule(args, graph, "godot", ":libgodot_android.so"),
        ]
    return [
        library,
        f"cc_binary(name = '_godot', visibility = ['//visibility:private'], deps = [':engine_library'], linkstatic = True, target_compatible_with = {compatibility!r})",
        _source_rule(args, graph, "godot", ":_godot"),
    ]


def _manifest(
    args: argparse.Namespace,
    graph: Mapping[str, Any],
    groups: Mapping[tuple[str, tuple[str, ...], tuple[str, ...]], Collection[str]],
    profile_scoped: bool,
) -> dict[str, Any]:
    swift_sources = graph["swift_sources"]
    return {
        "schema_version": 1,
        "version": args.version,
        "platform": args.platform,
        "cpu": args.cpu,
        "build_target": args.build_target,
        "requested_modules": args.modules,
        "selected_modules": graph["modules"],
        "object_actions": sum(len(set(sources)) for sources in groups.values())
        + len(set(swift_sources)),
        "swift_sources": sorted(set(swift_sources)),
        "compile_groups": len(groups),
        "generator_actions": len(graph["generators"]),
        "scons_options": args.options,
        "minimum_os": graph["minimum_os"],
        # Whether only class registrations see the build profile; a fork that changed
        # class_db.h gives it to every source.
        "build_profile_scoped": profile_scoped,
    }


def _includes(
    root: Path,
    compiled: Sequence[tuple[str, tuple[str, ...], tuple[str, ...], list[str]]],
    generated: Mapping[str, Generated],
    extra_roots: Sequence[str],
) -> tuple[Mapping[str, Collection[str]], set[str], bool]:
    """
    Return what each file includes, the sources that see the build profile, and whether
    only those do.
    """
    profile_scoped = build_profile.scope(root)
    includes = include_graph(
        root,
        (
            CompileGroup(sources, directories, copts)
            for _, copts, directories, sources in compiled
        ),
        generated,
        extra_roots,
    )
    if not profile_scoped:
        return includes, set(), False
    sources = [source for *_, group in compiled for source in group]
    includes, users = build_profile.declare(root, includes, generated, sources)
    return includes, users, True


def render(args: argparse.Namespace, graph: Mapping[str, Any], root: Path) -> None:
    """Write the BUILD file, generator specifications and manifest of a configured graph."""
    groups = {
        (language, tuple(copts), tuple(includes)): sources
        for language, copts, includes, sources in graph["groups"]
    }
    generators = [
        (generator["spec"], set(generator["dependencies"]))
        for generator in graph["generators"]
    ]
    lines = _header_rules(args, bool(graph["swift_sources"]))
    generator_rules, generated_headers = _generator_rules(root, generators)
    lines += generator_rules
    generated = generated_files(root, (spec for spec, _ in generators))
    compiled = object_groups(groups, generated_headers, generated)
    swift_options = graph["swift_options"] or _DEFAULT_SWIFT_OPTIONS
    swift_roots = [swift_options["bridging_header"]] if graph["swift_sources"] else []
    includes, profile_users, profile_scoped = _includes(
        root, compiled, generated, swift_roots
    )
    header_rules, targets = include_rules(includes)
    lines += header_rules
    objects, dependencies = object_rules(compiled, includes, targets, profile_users)
    lines += objects
    for bridging_header in swift_roots:
        deps = _source_deps(includes, targets, bridging_header)
        lines.append(_swift_rule(graph["swift_sources"], swift_options, deps))
        dependencies.append(":_swift")
    lines += _engine_rules(args, graph, dependencies)
    (root / "BUILD.bazel").write_text("\n\n".join(lines) + "\n")
    # This file is the successful-capture marker checked after SCons exits.
    write_json(
        root / "engine_manifest.json", _manifest(args, graph, groups, profile_scoped)
    )
