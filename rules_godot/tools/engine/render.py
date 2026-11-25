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
    from .generators import (
        generated_files,
        generator_rules,
        multiline_rule,
        spec_path,
    )
    from .include_graph import (
        CompileGroup,
        Generated,
        components,
        include_graph,
        reached_directories,
    )
    from .source_tree import write_json
except ImportError:
    import build_profile
    import define_analysis
    import variants
    from generators import (
        generated_files,
        generator_rules,
        multiline_rule,
        spec_path,
    )
    from include_graph import (
        CompileGroup,
        Generated,
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
        f'load("{args.generator_bzl}", "godot_source_generator", "godot_source_headers", "godot_source_library", "godot_source_binary", "godot_source_revision", "godot_define_analysis", "godot_source_defines", "godot_profile_independent")',
        # Without module maps, whose contents name the configuration's output directory, the
        # engine's compile actions keep one cache key in every configuration under path
        # mapping. The engine's sources, Swift's included, need none.
        'package(default_visibility = ["//visibility:public"], features = ["-module_maps", "-layering_check"])',
        'exports_files(["engine_manifest.json"])',
        f"godot_source_revision(name = 'revision', visibility = ['//visibility:private'], build_name = {args.build_name!r}, inputs_hash = {args.inputs_hash!r}, build = '_revision/build.txt', hash = '_revision/hash.txt', timestamp = '_revision/timestamp.txt')",
        # The source root's include directory, which every compile action searches.
        "cc_library(name = '_root', visibility = ['//visibility:private'], includes = ['.'])",
    ]
    return lines


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
    options: list[str] = []
    definitions: list[str] = []
    copts = list(copts)
    while copts:
        copt = copts.pop(0)
        if copt in ("-D", "-U") and copts:
            # The separate form, -D NAME, as one option.
            copt += copts.pop(0)
        (definitions if define_analysis.is_definition(copt) else options).append(copt)
    return [f"_COPTS_{index} = {options!r}", f"_DEFINES_{index} = {definitions!r}"]


# The tag that lets Bazel's path mapping (--experimental_output_paths=strip) give the engine's
# native actions one cache key in every configuration, such as the runtimes of applications
# with different build profiles; without that flag it changes nothing.
PATH_MAPPING = "tags = ['supports-path-mapping'], "


def _library_rules(language: str, library: define_analysis.Library) -> list[str]:
    """
    A source's library rule, with its define analysis if it is C or C++.

    Objective-C sources import implicit modules, which see only the command line's macros,
    and assembly sources are no C or C++: both keep their -D options.
    """
    common = (
        f"name = {library.name!r}, visibility = ['//visibility:private'], {PATH_MAPPING}"
    )
    rest = f"includes = {library.includes}, deps = {library.deps!r}, alwayslink = True)"
    if not define_analysis.analyzed(language, library.source):
        rule = "objc_library" if language == "objc" else "cc_library"
        copts = f"_COPTS_{library.group}" + (
            f" + _DEFINES_{library.group}" if language != "objc" else ""
        )
        defines = (
            f"local_defines = {library.local_defines!r}, "
            if library.local_defines
            else ""
        )
        return [
            f"{rule}({common}srcs = {[library.source]!r}, "
            + f"copts = {copts}, {defines}{rest}"
        ]
    header = define_analysis.header(library.name)
    return [
        define_analysis.defines_rule(library),
        f"cc_library({common}srcs = {[library.source, header]!r}, "
        + f"copts = _COPTS_{library.group} + ['-include', {header!r}], {rest}",
    ]


def object_rules(
    groups: Sequence[tuple[str, tuple[str, ...], tuple[str, ...], list[str]]],
    graph: Mapping[str, Collection[str]],
    targets: Mapping[str, str],
    profile_users: Container[str],
) -> tuple[list[str], list[str], list[define_analysis.Library]]:
    """
    Return a library rule per source, the labels of those libraries, and those whose
    definitions the define analysis writes.

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
    analyzed: list[define_analysis.Library] = []
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
            library = define_analysis.Library(
                group=index,
                source=source,
                name=name,
                includes=source_includes[source],
                deps=_source_deps(graph, targets, source),
                local_defines=[build_profile.DEFINE] if source in profile_users else [],
            )
            lines += _library_rules(language, library)
            if define_analysis.analyzed(language, source):
                analyzed.append(library)
    return lines, labels, analyzed


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
    return multiline_rule("swift_library", attributes)


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


# ==== Rendering ===============================================================


# The target that gathers the engine's objects that read no build profile.
_PROFILE_INDEPENDENT = ":_profile_independent_objects"


def engine_dependencies(
    labels: Sequence[str],
    readers: Collection[str],
    scoped: bool,
    runtime_profiles: Sequence[str] = (),
) -> tuple[list[str], list[str]]:
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
    independent = [label for label in labels if label not in readers]
    kept = f", runtime_profiles = {list(runtime_profiles)!r}" if runtime_profiles else ""
    rule = (
        f"godot_profile_independent(name = {_PROFILE_INDEPENDENT[1:]!r}, "
        f"visibility = ['//visibility:private'], deps = {independent!r}{kept})"
    )
    return [label for label in labels if label in readers] + [_PROFILE_INDEPENDENT], [
        rule
    ]


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
            f"objc_library(name = '_engine_library', visibility = ['//visibility:private'], {PATH_MAPPING}deps = {dependencies!r}, linkopts = {linkopts!r}, sdk_frameworks = {_IOS_FRAMEWORKS!r}, sdk_dylibs = ['c++', 'z', 'iconv'], target_compatible_with = {compatibility!r})",
            _source_rule(args, graph, "engine_library", ":_engine_library"),
        ]
    library = f"cc_library(name = 'engine_library', {PATH_MAPPING}deps = {dependencies!r}, linkopts = {linkopts!r}, target_compatible_with = {compatibility!r})"
    if args.platform == "android":
        return [
            library,
            f"cc_binary(name = 'libgodot_android.so', {PATH_MAPPING}deps = [':engine_library'], linkstatic = True, linkshared = True, target_compatible_with = {compatibility!r})",
            _source_rule(args, graph, "godot", ":libgodot_android.so"),
        ]
    return [
        library,
        f"cc_binary(name = '_godot', visibility = ['//visibility:private'], {PATH_MAPPING}deps = [':engine_library'], linkstatic = True, target_compatible_with = {compatibility!r})",
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
) -> Mapping[str, Collection[str]]:
    """Return what each file includes."""
    return include_graph(
        root,
        (
            CompileGroup(sources, directories, copts)
            for _, copts, directories, sources in compiled
        ),
        generated,
        extra_roots,
    )


def _profile_users(
    root: Path,
    compiled: Sequence[tuple[str, tuple[str, ...], tuple[str, ...], list[str]]],
    includes: Mapping[str, Collection[str]],
    generated: Mapping[str, Generated],
) -> tuple[Mapping[str, Collection[str]], set[str]]:
    """
    Return the include graph with the build profile where it is scoped, and its sources.

    Only the sources that register classes see it.
    """
    sources = [source for *_, group in compiled for source in group]
    return build_profile.declare(root, includes, generated, sources)


def _profile_readers(
    compiled: Sequence[tuple[str, tuple[str, ...], tuple[str, ...], list[str]]],
    labels: Sequence[str],
    profile_users: Container[str],
) -> set[str]:
    """Return the labels of the objects whose sources read the build profile."""
    # object_rules names one library per source, in the order of the compile groups.
    ordered = [source for *_, sources in compiled for source in sources]
    return {label for source, label in zip(ordered, labels) if source in profile_users}


class Rendered(NamedTuple):
    """A graph's BUILD statements without the define analysis, which they share."""

    statements: list[str]
    analyzed: list[define_analysis.Library]
    specs: dict[str, Mapping[str, Any]]
    manifest: dict[str, Any]


def render_graph(
    args: argparse.Namespace, graph: Mapping[str, Any], root: Path, scoped: bool
) -> Rendered:
    """Return the BUILD statements, generator specifications and manifest of a graph."""
    groups = {
        (language, tuple(copts), tuple(includes)): sources
        for language, copts, includes, sources in graph["groups"]
    }
    generators = [
        (generator["spec"], set(generator["dependencies"]))
        for generator in graph["generators"]
    ]
    lines = header_rules(args, bool(graph["swift_sources"]))
    generator_lines, generated_headers = generator_rules(args, root, generators)
    lines += generator_lines
    generated = generated_files(root, (spec for spec, _ in generators))
    compiled = object_groups(groups, generated_headers, generated)
    swift_options = graph["swift_options"] or _DEFAULT_SWIFT_OPTIONS
    swift_roots = [swift_options["bridging_header"]] if graph["swift_sources"] else []
    includes = _includes(root, compiled, generated, swift_roots)
    profile_users: set[str] = set()
    if scoped:
        includes, profile_users = _profile_users(root, compiled, includes, generated)
    include_lines, targets = include_rules(includes)
    lines += include_lines
    objects, dependencies, analyzed = object_rules(
        compiled, includes, targets, profile_users
    )
    lines += objects
    readers = _profile_readers(compiled, dependencies, profile_users)
    for bridging_header in swift_roots:
        deps = _source_deps(includes, targets, bridging_header)
        lines.append(_swift_rule(graph["swift_sources"], swift_options, deps))
        dependencies.append(":_swift")
    dependencies, independent = engine_dependencies(
        dependencies, readers, scoped, args.runtime_profiles
    )
    lines += independent
    lines += _engine_rules(args, graph, dependencies)
    specs = {spec_path(spec): spec for spec, _ in generators}
    return Rendered(lines, analyzed, specs, _manifest(args, graph, groups, scoped))


class Variant(NamedTuple):
    """
    A recipe's runtime variant: its registered runtime profile's label and configuration.

    graph is None where the variant has no current pin or cannot configure; error says why.
    """

    profile: str
    args: argparse.Namespace
    graph: Mapping[str, Any] | None
    error: str = ""


def _variant_settings(args: argparse.Namespace, settings: Mapping[str, str]) -> list[str]:
    """The config_setting of each variant: the build profile is its runtime profile."""
    return [
        f"config_setting(name = {setting[1:]!r}, visibility = ['//visibility:private'], "
        f"flag_values = {{{args.build_profile_label!r}: {profile!r}}})"
        for profile, setting in settings.items()
    ]


class _Variants(NamedTuple):
    """A recipe's runtime variants: their settings, rendered graphs and errors, by setting."""

    settings: dict[str, str]
    rendered: dict[str, Rendered]
    errors: dict[str, str]


def _render_variants(
    runtime_variants: Sequence[Variant], root: Path, scoped: bool
) -> _Variants:
    """Render the graph of each variant that has one, and name each one's config_setting."""
    settings = {
        variant.profile: f":_variant_{index}"
        for index, variant in enumerate(runtime_variants)
    }
    rendered = {}
    errors = {}
    for variant in runtime_variants:
        setting = settings[variant.profile]
        if variant.graph is None:
            errors[setting] = variant.error
        else:
            rendered[setting] = render_graph(variant.args, variant.graph, root, scoped)
    return _Variants(settings, rendered, errors)


def _shared_analysis(base: Rendered, rendered: Mapping[str, Rendered]) -> list[str]:
    """The define analysis of every variant's libraries, sharded by the variants that compile them."""
    graphs = {"": base, **rendered}
    libraries = {
        library.name: library for item in graphs.values() for library in item.analyzed
    }
    scopes = variants.presence_scopes(
        {
            setting: [library.name for library in item.analyzed]
            for setting, item in graphs.items()
        }
    )
    return define_analysis.analysis_rules(libraries.values(), scopes=scopes)


def _merge_variants(
    args: argparse.Namespace, base: Rendered, merged: _Variants
) -> tuple[list[str], dict[str, Mapping[str, Any]]]:
    """Return the statements and specifications of one package of every variant."""
    statements = variants.merge(
        base.statements,
        {setting: item.statements for setting, item in merged.rendered.items()},
    )
    statements += _variant_settings(args, merged.settings)
    statements += _shared_analysis(base, merged.rendered)
    if merged.errors:
        statements.insert(1, f'load("{args.pin_bzl}", "godot_unpinned_recipe")')
    statements = variants.unpinned_variants(
        statements, engine_targets(args.platform), merged.errors
    )
    specs = dict(base.specs)
    for item in merged.rendered.values():
        specs.update(item.specs)
    return statements, specs


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
    scoped = build_profile.scope(root)
    base = render_graph(args, graph, root, scoped)
    if runtime_variants:
        merged = _render_variants(runtime_variants, root, scoped)
        statements, specs = _merge_variants(args, base, merged)
    else:
        statements = base.statements + define_analysis.analysis_rules(base.analyzed)
        specs = base.specs
    for path, spec in specs.items():
        write_json(root / path, spec)
    (root / "BUILD.bazel").write_text("\n\n".join(statements) + "\n")
    manifest = base.manifest | {
        "runtime_variants": {
            variant.profile: variant.error or "configured" for variant in runtime_variants
        }
    }
    # This file is the successful-capture marker checked after SCons exits.
    write_json(root / "engine_manifest.json", manifest)
