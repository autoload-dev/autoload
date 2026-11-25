"""
Render a configured engine graph as the BUILD file of its recipe repository.

The graph comes from Godot's SCons configuration, now or from a recipe's pin. Rendering
reads the extracted tree, but the graph does not depend on it, so a recipe's pin does
not cover this module: changing how a graph renders keeps every pin.

Sections: Build facts, Unpinned engines, Native rules, Swift and sources, Rendering.
"""

import argparse
from collections.abc import Collection, Container, Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any, NamedTuple

try:
    from . import build_profile, define_analysis, variants
    from .build_file import Constants, Plus, Rule, write
    from .generators import generated_files, generator_rules, spec_path
    from .include_graph import (
        CompileGroup,
        Generated,
        TreeCache,
        components,
        include_graph,
        reached_directories,
    )
    from .source_tree import write_json
except ImportError:
    import build_profile
    import define_analysis
    import variants
    from build_file import Constants, Plus, Rule, write
    from generators import generated_files, generator_rules, spec_path
    from include_graph import (
        CompileGroup,
        Generated,
        TreeCache,
        components,
        include_graph,
        reached_directories,
    )
    from source_tree import write_json


# ==== Build facts =============================================================


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


# ==== Unpinned engines ========================================================


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


# ==== Native rules ============================================================


def header_rules(args: argparse.Namespace, uses_swift: bool) -> list[str]:
    """Return the loads and package statements that open the BUILD file."""
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
        f'load("{args.generator_bzl}", "godot_source_generator", "godot_source_headers", "godot_source_library", "godot_source_binary", "godot_source_revision", "godot_define_analysis", "godot_source_defines", "godot_profile_independent")',
        # Without module maps, whose contents name the configuration's output directory, the
        # engine's compile actions keep one cache key in every configuration under path
        # mapping. The engine's sources, Swift's included, need none.
        'package(default_visibility = ["//visibility:public"], features = ["-module_maps", "-layering_check"])',
        'exports_files(["engine_manifest.json"])',
    ]
    return lines


_PRIVATE = ["//visibility:private"]


def common_rules(args: argparse.Namespace) -> list[Rule]:
    """The revision target and the source root's include directory."""
    return [
        Rule(
            "godot_source_revision",
            "revision",
            {
                "visibility": _PRIVATE,
                "build_name": args.build_name,
                "inputs_hash": args.inputs_hash,
                "build": "_revision/build.txt",
                "hash": "_revision/hash.txt",
                "timestamp": "_revision/timestamp.txt",
            },
            fixed=frozenset({"build", "hash", "timestamp"}),
        ),
        # The source root's include directory, which every compile action searches.
        Rule("cc_library", "_root", {"visibility": _PRIVATE, "includes": ["."]}),
    ]


def include_rules(
    graph: Mapping[str, Collection[str]],
) -> tuple[list[Rule], dict[str, str]]:
    """
    Return a header target per set of files that include each other, and each file's target.

    Each target depends on the targets of the files its files include, so a compile
    action's inputs are what its source reaches.
    """
    included = {name for names in graph.values() for name in names}
    rules: list[Rule] = []
    targets: dict[str, str] = {}
    for component in components(graph):
        if included.isdisjoint(component):
            continue
        label = ":_includes/" + component[0]
        targets.update((file, label) for file in component)
        deps = sorted(
            {targets[include] for file in component for include in graph[file]} - {label}
        )
        rules.append(
            Rule("godot_source_headers", label[1:], {"hdrs": component, "deps": deps})
        )
    return rules, targets


def _source_deps(
    graph: Mapping[str, Collection[str]], targets: Mapping[str, str], source: str
) -> list[str]:
    """The source root's include directory and the header targets of a source's includes."""
    return [":_root", *sorted({targets[name] for name in graph[source]})]


def object_library_name(source: str, group: int, taken: Container[str]) -> str:
    """
    Return the name of a source's library, which objc_library allows no slash in.

    A source that another compile group also compiles, or whose name another source's
    flattened path takes, adds its group's index.
    """
    name = "_objects__" + source.replace("/", "__")
    return name if name not in taken else f"{name}__{group}"


def _split_definitions(copts: Sequence[str]) -> tuple[list[str], list[str]]:
    """A C or C++ group's options and its -D and -U options, apart."""
    options: list[str] = []
    definitions: list[str] = []
    copts = list(copts)
    while copts:
        copt = copts.pop(0)
        if copt in ("-D", "-U") and copts:
            # The separate form, -D NAME, as one option.
            copt += copts.pop(0)
        (definitions if define_analysis.is_definition(copt) else options).append(copt)
    return options, definitions


# The tag that lets Bazel's path mapping (--experimental_output_paths=strip) give the engine's
# native actions one cache key in every configuration, such as the runtimes of applications
# with different build profiles; without that flag it changes nothing.
PATH_MAPPING = ["supports-path-mapping"]


def _library_rules(language: str, library: define_analysis.Library) -> list[Rule]:
    """
    A source's library rule, with its define analysis if it is C or C++.

    Objective-C sources import implicit modules, which see only the command line's macros,
    and assembly sources are no C or C++: both keep their -D options.
    """
    common: dict[str, object] = {"visibility": _PRIVATE, "tags": PATH_MAPPING}
    rest: dict[str, object] = {
        "includes": library.includes,
        "deps": library.deps,
        "alwayslink": True,
    }
    if not define_analysis.analyzed(language, library.source):
        kind = "objc_library" if language == "objc" else "cc_library"
        copts = (
            library.copts
            if language == "objc"
            else Plus((library.copts, library.defines))
        )
        defines = (
            {"local_defines": library.local_defines} if library.local_defines else {}
        )
        attrs = common | {"srcs": [library.source], "copts": copts} | defines | rest
        return [Rule(kind, library.name, attrs)]
    header = define_analysis.header(library.name)
    attrs = common | {
        "srcs": [library.source, header],
        "copts": Plus((library.copts, ["-include", header])),
    }
    return [
        define_analysis.defines_rule(library),
        Rule("cc_library", library.name, attrs | rest),
    ]


class Includes(NamedTuple):
    """What each file includes, each file's header target, and the sources that see the profile."""

    graph: Mapping[str, Collection[str]]
    targets: Mapping[str, str]
    profile_users: Container[str]


class Objects(NamedTuple):
    """The library rules of a graph's sources and what the engine library needs of them."""

    rules: list[Rule]
    labels: list[str]
    readers: set[str]
    analyzed: list[define_analysis.Library]


def _group_options(
    language: str, copts: Sequence[str]
) -> tuple[list[str], list[str] | None]:
    """A group's options and -D options; Objective-C keeps them together."""
    if language == "objc":
        return list(copts), None
    return _split_definitions(copts)


def object_rules(
    groups: Sequence[tuple[str, tuple[str, ...], tuple[str, ...], list[str]]],
    includes: Includes,
    constants: Constants | None = None,
) -> Objects:
    """
    Return a library rule per source, the labels of those libraries, those whose sources
    read the build profile, and those whose definitions the define analysis writes.

    A library is named after its source, so its object keeps its path, and its cache key,
    when other compile groups of the engine change. Sources that register classes see
    the build profile. A source compiles with only the include directories that hold a
    file it reaches. C and C++ sources take their macro definitions from the define
    analysis; Objective-C sources, which import implicit modules, keep their -D options.
    """
    constants = constants or Constants()
    reached = reached_directories(
        includes.graph, {directory for _, _, dirs, _ in groups for directory in dirs}
    )
    result = Objects([], [], set(), [])
    names: set[str] = set()
    for index, (language, copts, directories, sources) in enumerate(groups):
        options, definitions = _group_options(language, copts)
        for source in sources:
            name = object_library_name(source, index, names)
            names.add(name)
            reads = source in includes.profile_users
            library = define_analysis.Library(
                source=source,
                name=name,
                copts=constants.ref("_COPTS", options),
                defines=None
                if definitions is None
                else constants.ref("_DEFINES", definitions),
                includes=constants.ref(
                    "_INCLUDES", [d for d in directories if d in reached[source]]
                ),
                deps=_source_deps(includes.graph, includes.targets, source),
                local_defines=[build_profile.DEFINE] if reads else [],
            )
            result.labels.append(":" + name)
            result.readers.update([":" + name] if reads else [])
            result.rules.extend(_library_rules(language, library))
            if define_analysis.analyzed(language, source):
                result.analyzed.append(library)
    return result


# ==== Swift and sources =======================================================


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


_DEFAULT_SWIFT_OPTIONS: dict[str, Any] = {
    "module_name": "godot_swift_module",
    "bridging_header": "drivers/apple_embedded/bridging_header_apple_embedded.h",
    "generated_header": None,
    "copts": ["-swift-version", "6", "-cxx-interoperability-mode=default"],
}


def _swift_rule(
    swift_sources: Iterable[str], options: Mapping[str, Any], deps: list[str]
) -> Rule:
    attributes: dict[str, object] = {
        "visibility": _PRIVATE,
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
    return Rule("swift_library", "_swift", attributes)


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
) -> Rule:
    """Return the rule that publishes a built library with the engine's provenance."""
    kind = (
        "godot_source_library"
        if args.platform in {"android", "ios"}
        else "godot_source_binary"
    )
    attrs: dict[str, object] = {
        "deps": [library],
        "version": graph["version"],
        "build": "_revision/build.txt",
        "hash": "_revision/hash.txt",
        "digest": "sha256:" + args.source_sha256 if args.source_sha256 else "",
        "customizations": args.customizations,
        "minimum_os": graph["minimum_os"],
        **source_build_facts(args),
    }
    if args.renderers:
        attrs |= {"renderers": args.engine_renderers, "declares_renderers": True}
    return Rule(kind, name, attrs)


# ==== Rendering ===============================================================


# The target that gathers the engine's objects that read no build profile.
_PROFILE_INDEPENDENT = ":_profile_independent_objects"


def engine_dependencies(
    labels: Sequence[str],
    readers: Collection[str],
    scoped: bool,
    runtime_profiles: Sequence[str] = (),
) -> tuple[list[str], list[Rule]]:
    """
    Return the engine library's dependencies and the rule that gathers the others.

    Only the objects of the sources that register classes read a build profile. The others
    sit behind a rule whose transition resets an application's profile, so applications with
    different profiles share them; a registered runtime profile stays, since it selects the
    runtime variant they compile in. A tree whose class_db.h gives the profile to every
    source, as a fork's may, keeps every object with the library.
    """
    if not scoped:
        return list(labels), []
    attrs: dict[str, object] = {
        "visibility": _PRIVATE,
        "deps": [label for label in labels if label not in readers],
    }
    if runtime_profiles:
        attrs["runtime_profiles"] = list(runtime_profiles)
    rule = Rule("godot_profile_independent", _PROFILE_INDEPENDENT[1:], attrs)
    return [label for label in labels if label in readers] + [_PROFILE_INDEPENDENT], [
        rule
    ]


def _engine_rules(
    args: argparse.Namespace, graph: Mapping[str, Any], dependencies: list[str]
) -> list[Rule]:
    """Return the rules of the platform's engine targets."""
    # Android's libgodot is a shared library. iOS consumers link engine_library
    # through rules_apple; cc_binary is the desktop executable/editor.
    compatibility: dict[str, object] = {
        "target_compatible_with": target_constraints(args)
    }
    native: dict[str, object] = {"tags": PATH_MAPPING}
    if args.platform == "ios":
        library = {
            "visibility": _PRIVATE,
            "deps": dependencies,
            "linkopts": graph["linkopts"],
            "sdk_frameworks": _IOS_FRAMEWORKS,
            "sdk_dylibs": ["c++", "z", "iconv"],
        }
        return [
            Rule("objc_library", "_engine_library", native | library | compatibility),
            _source_rule(args, graph, "engine_library", ":_engine_library"),
        ]
    library: dict[str, object] = {"deps": dependencies, "linkopts": graph["linkopts"]}
    rules = [Rule("cc_library", "engine_library", native | library | compatibility)]
    linked: dict[str, object] = {"deps": [":engine_library"], "linkstatic": True}
    if args.platform == "android":
        shared = native | linked | {"linkshared": True} | compatibility
        return rules + [
            Rule("cc_binary", "libgodot_android.so", shared),
            _source_rule(args, graph, "godot", ":libgodot_android.so"),
        ]
    private = native | {"visibility": _PRIVATE} | linked | compatibility
    return rules + [
        Rule("cc_binary", "_godot", private),
        _source_rule(args, graph, "godot", ":_godot"),
    ]


def _manifest(
    args: argparse.Namespace, graph: Mapping[str, Any], profile_scoped: bool
) -> dict[str, Any]:
    swift_sources = graph["swift_sources"]
    groups = {
        (group[0], tuple(group[1]), tuple(group[2])): group[3]
        for group in graph["groups"]
    }
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


class Tree(NamedTuple):
    """
    The extracted source tree a recipe's graphs render from, and what they share of it.

    scoped says whether only the sources that register classes see the build profile; a
    fork that changed class_db.h gives it to every source.
    """

    root: Path
    scoped: bool
    cache: TreeCache
    constants: Constants


class Rendered(NamedTuple):
    """A graph's rules without the define analysis, which the variants share."""

    rules: list[Rule]
    analyzed: list[define_analysis.Library]
    readers: set[str]
    specs: dict[str, Mapping[str, Any]]
    manifest: dict[str, Any]


def _python_files(tree: Tree) -> list[str]:
    return sorted(name for name in tree.cache.files() if name.endswith(".py"))


def _sources(
    args: argparse.Namespace, graph: Mapping[str, Any], tree: Tree
) -> tuple[list[Rule], Mapping[str, Generated], list[Any]]:
    """Return the generator rules, the generated files and the compile groups of a graph."""
    groups = {
        (language, tuple(copts), tuple(includes)): sources
        for language, copts, includes, sources in graph["groups"]
    }
    generators = [
        (generator["spec"], set(generator["dependencies"]))
        for generator in graph["generators"]
    ]
    rules, generated_headers = generator_rules(
        generators, _python_files(tree), args.recipe_profile, args.registered_profile
    )
    generated = generated_files(tree.root, (spec for spec, _ in generators))
    return rules, generated, object_groups(groups, generated_headers, generated)


def _includes(
    tree: Tree,
    compiled: Sequence[Any],
    generated: Mapping[str, Generated],
    roots: Sequence[str],
) -> Includes:
    """What each file includes, with the build profile only where sources register classes."""
    graph: Mapping[str, Collection[str]] = include_graph(
        tree.cache,
        (CompileGroup(sources, dirs, copts) for _, copts, dirs, sources in compiled),
        generated,
        roots,
    )
    users: set[str] = set()
    if tree.scoped:
        sources = [source for *_, group in compiled for source in group]
        graph, users = build_profile.declare(tree.root, graph, generated, sources)
    _, targets = include_rules(graph)
    return Includes(graph, targets, users)


def render_graph(
    args: argparse.Namespace, graph: Mapping[str, Any], tree: Tree
) -> Rendered:
    """Return the rules, generator specifications and manifest of a graph."""
    rules, generated, compiled = _sources(args, graph, tree)
    rules = common_rules(args) + rules
    swift_options = graph["swift_options"] or _DEFAULT_SWIFT_OPTIONS
    swift_roots = [swift_options["bridging_header"]] if graph["swift_sources"] else []
    includes = _includes(tree, compiled, generated, swift_roots)
    rules += include_rules(includes.graph)[0]
    objects = object_rules(compiled, includes, tree.constants)
    rules += objects.rules
    dependencies = list(objects.labels)
    for bridging_header in swift_roots:
        deps = _source_deps(includes.graph, includes.targets, bridging_header)
        rules.append(_swift_rule(graph["swift_sources"], swift_options, deps))
        dependencies.append(":_swift")
    dependencies, independent = engine_dependencies(
        dependencies, objects.readers, tree.scoped, args.runtime_profiles
    )
    rules += independent + _engine_rules(args, graph, dependencies)
    specs = {spec_path(item["spec"]): item["spec"] for item in graph["generators"]}
    manifest = _manifest(args, graph, tree.scoped)
    return Rendered(rules, objects.analyzed, objects.readers, specs, manifest)


class Variant(NamedTuple):
    """
    A recipe's runtime variant: its registered runtime profile's label and configuration.

    graph is None where the variant has no current pin or cannot configure; error says why.
    """

    profile: str
    args: argparse.Namespace
    graph: Mapping[str, Any] | None
    error: str = ""


def _variant_setting(args: argparse.Namespace, profile: str, setting: str) -> Rule:
    """The config_setting of a variant: the build profile is its runtime profile."""
    return Rule(
        "config_setting",
        setting[1:],
        {"visibility": _PRIVATE, "flag_values": {args.build_profile_label: profile}},
    )


def _shared_analysis(graphs: Mapping[str, Rendered]) -> list[Rule]:
    """
    The define analysis of every variant's libraries.

    A shard holds the libraries that the same variants compile; those whose sources read the
    build profile have shards of their own, since they compile in the application's
    configuration rather than the shared one.
    """
    libraries = {
        library.name: library for item in graphs.values() for library in item.analyzed
    }
    scopes = variants.presence_scopes(
        {
            setting: [library.name for library in item.analyzed]
            for setting, item in graphs.items()
        }
    )
    readers = {label[1:] for item in graphs.values() for label in item.readers}
    for name in readers.intersection(scopes):
        scopes[name] = "r__" + scopes[name]
    return define_analysis.analysis_rules(libraries.values(), scopes=scopes)


def _package_rules(
    args: argparse.Namespace,
    base: Rendered,
    runtime_variants: Sequence[Variant],
    tree: Tree,
) -> list[Rule]:
    """The rules of one package of the base and every variant, with their analysis."""
    settings = {
        variant.profile: f":_variant_{index}"
        for index, variant in enumerate(runtime_variants)
    }
    graphs = {"": base} | {
        settings[variant.profile]: render_graph(variant.args, variant.graph, tree)
        for variant in runtime_variants
        if variant.graph is not None
    }
    rules = variants.merge(
        base.rules,
        {setting: item.rules for setting, item in graphs.items() if setting},
    )
    rules += [
        _variant_setting(args, profile, setting) for profile, setting in settings.items()
    ]
    rules += _shared_analysis(graphs)
    errors = {
        settings[variant.profile]: variant.error
        for variant in runtime_variants
        if variant.graph is None
    }
    for item in graphs.values():
        base.specs.update(item.specs)
    return variants.unpinned_variants(rules, engine_targets(args.platform), errors)


def render(
    args: argparse.Namespace,
    graph: Mapping[str, Any],
    root: Path,
    runtime_variants: Sequence[Variant] = (),
) -> None:
    """
    Write the BUILD file, generator specifications and manifest of a configured graph.

    With runtime variants, the package declares each variant's graph too, selected by the
    build profile.
    """
    tree = Tree(root, build_profile.scope(root), TreeCache(root), Constants())
    base = render_graph(args, graph, tree)
    rules = _package_rules(args, base, runtime_variants, tree)
    header = header_rules(args, bool(graph["swift_sources"]))
    if any(variant.graph is None for variant in runtime_variants):
        header.insert(1, f'load("{args.pin_bzl}", "godot_unpinned_recipe")')
    for path, spec in base.specs.items():
        write_json(root / path, spec)
    (root / "BUILD.bazel").write_text(write(header, tree.constants.values, rules))
    manifest = base.manifest | {
        "runtime_variants": {
            variant.profile: variant.error or "configured" for variant in runtime_variants
        }
    }
    # This file is the successful-capture marker checked after SCons exits.
    write_json(root / "engine_manifest.json", manifest)
